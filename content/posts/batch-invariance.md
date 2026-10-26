---
title: the same token gets a different answer when my gpu checks it in a batch
date: 2026-10-26
description: speculative decoding promises the exact output of the big model. on my laptop gpu it changed the text, because the big model's logits for a token depend on how many other tokens share the pass. the reasons, down to the warp and the attention block, and how each one was made bit-exact.
tags: LLM Inference, GPU, CUDA, llama.cpp
---
i was trying to get speculative decoding working faster on my laptop when i noticed that it was changing the model's output. i wasn't sampling, and i wasn't changing prompts between runs. the only difference was whether the big model generated tokens one at a time or verified several of them together. i started comparing the calculations behind those two paths and found differences in the cuda kernels used for quantized matrix multiplication and attention. this post is about where those differences came from, the fixes i tried, and what the fixes cost in performance.

code, patches and logs: [github.com/Cintu07/hiraishin](https://github.com/Cintu07/hiraishin).

my setup was qwen3-8b with greedy decoding on an rtx 5060 laptop gpu with 8 gb of vram. in one test, ordinary decoding wrote "`get(key)` to retrieve a value by key." the speculative run, given the same prompt, wrote "`get(key)` to retrieve a value" and then continued with a different sentence. out of my first 24 speculative runs, only 8 matched ordinary decoding. the other 16 diverged at some point, and each divergence appeared at the same byte when i repeated the run. that made me suspect a deterministic difference between the execution paths rather than randomness.

the acceptance rule used in greedy speculative decoding is supposed to reproduce the big model's choices. but that assumes the big model makes the same choice when it verifies a token in a batch as it does when it decodes that token alone. the actual gpu implementation doesn't automatically guarantee this. i wanted to go beyond comparing the final text and find out why the logits themselves were moving.

![fig. 1: one forward pass on this laptop, drawn to scale. the read of the weights is almost the whole cost, so a second token in the same pass is nearly free.](/assets/img/hiraishin/fig-01.png)

## why processing several tokens together helps

in decoding, the gpu spends a lot of time moving model weights from memory. the q4_k_m version of qwen3-8b takes about 4.67 gb, and my laptop's memory bandwidth is roughly 286 gb/s. dividing the weight size by that bandwidth gives a best-case weight-read time of around 16.3 ms. i measured 19.1 ms for a one-token forward pass. when i put two tokens into the same pass, it took 19.5 ms, so the extra token added only 0.4 ms in that test. the weights were already being read for the first token, and the gpu could use them for the second token without repeating the whole transfer.

![fig. 2: a small model guesses ahead and the big model checks every guess in one pass. a guess is kept only if it equals what the big model picks on its own.](/assets/img/hiraishin/fig-02.png)

i used qwen3-0.6b as the draft model. it proposes a few tokens, and qwen3-8b verifies the proposals together. with greedy decoding, a proposal is accepted only when it matches the big model's highest-logit token at that position. that saves work if several proposals are correct, because one expensive pass can verify more than one token. the catch is that the verification pass has to agree with normal sequential decoding. strictly speaking, the winning tokens need to match for the final greedy output to stay the same; identical logits are a stronger condition. i decided to target the stronger condition because even a small logit difference can flip the winner when two candidates are close.

## where the numerical differences start

fp32 addition isn't associative. a float has 24 bits of significand precision, so near 100,000,000 the spacing between representable numbers is 8. evaluating `(100000000 + 1) - 100000000` in fp32 gives 0, because the first addition rounds away the 1. but `(100000000 - 100000000) + 1` gives 1. the numbers are the same; the order of additions is different. transformer inference contains huge numbers of dot products, and gpus split those sums between threads and warps rather than doing every addition sequentially. if a kernel launch changes which thread accumulates which values, it can also change the rounding in the final result.

![fig. 3: three numbers in two orders give two answers. a mat-vec splits each row's sum across warps, and the warp count changes with the number of tokens in the pass.](/assets/img/hiraishin/fig-03.png)

## the quantized mat-vec kernel

the first place i found the problem was `mul_mat_vec_q`, the quantized matrix-vector kernel llama.cpp uses during decoding. consider one row of a q6_k weight matrix with 4096 inputs. the weights are packed in blocks of 256, so that row has 16 weight blocks, while the activations are quantized to 8-bit values in blocks of 32. the inner dot product uses `dp4a`, which multiplies four pairs of int8 values and accumulates them into an int32 result. assuming there's no integer overflow, that part isn't affected by summation order. the floating-point differences enter when the integer dot-product results are scaled using the quantization scales and added to an fp32 accumulator.

a cuda block handles each row using `nwarps` warps, with 32 threads per warp. those threads walk through parts of the row using this loop:

```cpp
constexpr int blocks_per_iter = vdr * nwarps*warp_size / qi;
for (int kbx = tid / (qi/vdr); kbx < blocks_per_row_x; kbx += blocks_per_iter) {
    tmp[j][i] += vec_dot_q_cuda(vx, &y[j*stride_col_y + kby], kbx_offset + i*stride_row_x + kbx, kqs);
}
```

for q6_k, `qi` is 32 and `vdr` is 1, making `blocks_per_iter` equal to `nwarps`. with 4 warps, warp 0 accumulates blocks 0, 4, 8 and 12; warp 1 accumulates blocks 1, 5, 9 and 13; and the other warps follow the same pattern. with 2 warps, warp 0 instead handles all eight even-numbered blocks. that's a different accumulation order for the same weights and inputs. after the loop, the other warps write their partial sums to shared memory, warp 0 combines them, and a warp reduction folds the 32 lane results together:

```cpp
for (int l = 0; l < nwarps-1; ++l) {
    tmp[j][i] += tmp_shared[l][j][i][threadIdx.x];
}
tmp[j][i] = warp_reduce_sum<warp_size>(tmp[j][i]);
```

the important part is that `nwarps` comes from a table keyed by the number of output columns, which here corresponds to the number of tokens being processed. on my gpu, 1 to 4 tokens use 4 warps and 5 to 8 use 2. a batch of 5 can therefore give a token a different arithmetic order from a single-token pass. at larger batch sizes, k-quant weights can move to a separate tiled matrix multiplication kernel called mmq, which is optimized for throughput and uses another accumulation strategy. fixing the warp count alone wouldn't help if verification switched to that kernel.

i treated the ordinary single-token result as the reference and left that path alone. for batched launches, i changed `calc_nwarps` so the batch-invariant path asks for the warp configuration that would have been used with one column:

```cpp
static constexpr int calc_nwarps(ggml_type type, int ncols_dst, mmvq_parameter_table_id table_id,
                                 bool small_k = false, bool halve_iters = false, bool bi = false) {
    if (bi && ncols_dst > 1 && ncols_dst <= MMVQ_MAX_BATCH_SIZE) {
        return calc_nwarps(type, 1, table_id, small_k, halve_iters, false);
    }
    // ... the stock table
}
```

using the single-column warp count keeps each column's traversal and reduction order aligned with the reference path. a block can still process a different number of rows because separate rows don't accumulate into one another. i also kept the batch-invariant path on this matrix-vector implementation for batches of up to 16 tokens instead of switching to mmq. more than 8 columns are split into smaller launches, which doesn't alter the arithmetic within an individual column. this wasn't an attempt to get a more accurate mathematical result; it was an attempt to reproduce the original implementation's exact floating-point behavior.

## attention and the replay test

attention introduced another execution difference. llama.cpp uses a vector flash-attention kernel for a single query, but multiple queries can switch to a tensor-core implementation that divides the calculation differently. my fork already had `GGML_CUDA_BATCH_INVARIANT`, which kept the vector attention path for up to 8 queries. i extended that limit to 16, so a batch of 9 wouldn't switch kernels just because of its size.

comparing finished generations wasn't a good debugging test. once two runs choose different tokens, their contexts differ, so every later logit comparison is contaminated by the earlier divergence. instead, i ran normal decoding, recorded the token sequence and the top logits, and replayed that same sequence in batches of different sizes. the inputs at each position stayed the same; only the execution shape changed. it was effectively verification with a perfect draft sequence, which made it possible to find numerical mismatches before they turned into different text.

with stock kernels, even batches of 2 changed the argmax at up to 4 positions per prompt. the gaps between the original top two logits at those positions were only 0.008 to 0.28, and some batched logits shifted by as much as 3.7. the fork's existing batch-invariant switch made batches of 2 and 3 bit-exact on three of my four prompts, but batches of 5 and 9 still had flips. that fit the kernel behavior: batches of 2 and 3 shared the single-token 4-warp geometry, while 5 did not, and 9 also exceeded the old vector-attention limit. with the mat-vec change and the higher attention limit, those mismatches went away. one longer prompt still had a separate issue.

![fig. 4: llama.cpp rounds the attention range up to a multiple of 256 cells. a token inside a batch that crosses 256 attends over a different range than the same token decoded alone.](/assets/img/hiraishin/fig-04.png)

## the 256-cell kv-cache boundary

while reading the kv-cache code, i found another difference between single-token decoding and a batched verification pass. llama.cpp pads the attention range rather than always using exactly the number of populated cache cells. `get_n_kv` rounds the range up, with a minimum padding granularity of 256 cells:

```cpp
const uint32_t n_pad_cur = std::max(n_pad, 256u);
result = std::max(std::min(cells.size(), std::max(n_pad_cur, GGML_PAD(cells.used_max_p1(), n_pad_cur))), result);
```

if token 255 is decoded alone, the cache is populated through position 255 and the padded range is 256 cells. but if position 255 is included in a verification batch covering positions 254 through 257, the populated range extends through 257 and gets padded to 512. the extra cells are masked to negative infinity before the softmax, so their exponentials contribute zero. i couldn't establish that this padding difference, by itself, changed a logit. i found the difference in the code, noticed that a larger attention range could affect work partitioning, and guarded against it before testing that specific scenario independently. i'm not counting it as a separately reproduced numerical bug.

the guard doesn't require a cuda change. i stop a verification batch before it crosses a multiple-of-256 boundary, then start the next batch on the other side. for example, one batch can end at position 255 and the next can start at 256. this occasionally reduces the number of draft tokens verified together, but it also removes that particular difference in the padded range while debugging the remaining issue.

![fig. 5: attention sums the kv cache in parallel blocks, and how many blocks comes from occupancy. a query whose last chunk holds real cells gets a different sum when that chunk joins another block.](/assets/img/hiraishin/fig-05.png)

## why the last mismatch appeared at position 390

with the mat-vec fix, the higher attention limit and the cache-boundary guard, three of the four prompts matched bit for bit at the batch sizes i tested. the fourth, a longer rewrite prompt, still had a logit difference of 0.338 with every batch size from 2 upward. the winning token didn't change, so a text-only test would have passed. the replay showed that the first difference appeared at kv position 390, while the other prompts never went past position 384. that gave me a useful boundary to investigate.

the vector attention kernel divides the kv cache into chunks of 128 cells. it can distribute those chunks over `P` parallel cuda blocks. block `y` processes chunks `y`, `y + P`, `y + 2P` and so on, keeping its own running maximum and sum. a later kernel merges the partial results. choosing `P` therefore determines which chunks are accumulated together. the initial value comes from a cuda occupancy query:

```cpp
int max_blocks_per_sm = 1;
CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&max_blocks_per_sm, fattn_kernel,
    block_dim.x * block_dim.y * block_dim.z, nbytes_shared));
int parallel_blocks = max_blocks_per_sm;
```

there's another search for wave efficiency after the occupancy query, capped by the number of chunks, but the starting point is the occupancy of the actual kernel being launched. the one-query and two-query versions are different compiled kernels. if they use different numbers of registers, they can support different numbers of active blocks per sm. that can lead to a different value of `P` even though both launches are using vector attention.

for a padded range of 512 cells, there are four 128-cell chunks. a query at position 300 can only attend to populated positions through 300, so the fourth chunk, covering positions 384 to 511, is fully masked. changing whether that empty chunk has its own parallel block or shares one with another chunk doesn't change the useful sum. at position 390, however, some values in the fourth chunk are real. with `P = 4`, chunk 3 gets its own partial accumulation; with `P = 3`, it joins chunk 0 in the same block. those are different addition orders, and they can round differently. this explained both the threshold near position 384 and why the shorter prompts had missed it.

i changed the batch-invariant launch so its occupancy calculation refers to the single-query kernel instead of the batched kernel:

```cpp
fattn_kernel_t occupancy_kernel = nullptr;
if (cols_per_block > 1 && ggml_cuda_batch_invariant()) {
    occupancy_kernel = flash_attn_ext_vec<D, 1, type_K, type_V, use_logit_softcap>;
}
```

the batch-invariant path was already sizing the wave-efficiency search as if it had a single-query tile. using the single-query occupancy estimate as well made the chunk partitioning line up with the reference path in my tests.

## results and the cost of keeping the math the same

that final change cleared the replay mismatch. the top-1 logit difference reported by the test was 0.000000 at batch sizes 2, 3, 5, 9 and 16 on the long prompt that had exposed the occupancy issue. i also tested batches of 2, 3, 5, 8, 9 and 12 on two other prompts, with qwen3-8b in both q4_k_m and q6_k. the compared results matched bit for bit. end to end, 208 out of 208 speculative runs reproduced normal greedy decoding token for token.

on another 45 prompts covering code, math, explanations, summaries, structured output, creative writing and long documents, including inputs up to 2,639 tokens, speculative and normal decoding matched on all 45. i also checked normal decoding on the patched build against normal decoding on the stock build; those 45 outputs matched too. that last check matters because i didn't want to make the two execution paths agree by accidentally changing the single-token reference. these are results for the tested models and configurations, not a proof that every model and gpu will behave identically.

![fig. 6: the price of exactness. stock is cheap past 5 tokens because it switches to a faster kernel whose sums are not bit-identical to a single token.](/assets/img/hiraishin/fig-06.png)

keeping the batched work on the mat-vec path was expensive. at 9 tokens, my first exact version took 3.33 times as long as a single-token pass, compared with 1.28 times for the faster stock path that could switch to mmq. the multi-column kernel was using as many as 168 registers per thread, while the single-column kernel used 48. higher register usage limits how many warps can be resident on an sm, which makes it harder for the gpu to hide memory latency. i wrote a dedicated q4_k and q6_k path that kept the same per-column dot products while sharing some weight-unpacking work across rows. at 128 registers per thread, without spills, and targeting four resident blocks per sm, the 9-token pass came down to 1.96 times the single-token cost. that's still slower than the stock path, but it remained bit-exact in the tests.

## what i took away from it

i'd expected the main challenge to be getting enough accepted draft tokens to make speculative decoding worthwhile. instead, i spent much of the work figuring out why the big model didn't always agree with its own single-token execution. the two measured mechanisms were a different floating-point summation order caused by batch-dependent launch geometry, and a different attention chunk assignment caused by occupancy-dependent parallelism. the second was particularly easy to miss because it only affected useful data after the context crossed the 384-position chunk boundary.

this isn't unique to speculative decoding. an inference engine can choose different kernels or work partitions for different tensor shapes and still be implementing the same mathematical model. but mathematically equivalent operations don't automatically give identical floating-point results. for greedy speculative decoding, a difference only changes the text when it flips the winning token; if the goal is bit-exact verification, even differences that leave the winner unchanged matter. replaying a fixed token sequence across batch sizes turned out to be the most useful way to see exactly where those differences began. now the remaining work is getting more of the stock kernel's speed back without changing the arithmetic again.
