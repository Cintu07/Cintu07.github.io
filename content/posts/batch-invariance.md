---
title: why speculative decoding changed my output
date: 2026-10-26
description: greedy speculative decoding is supposed to reproduce the big model exactly. on my laptop it changed the text in 16 of 24 runs. the cause was three places where a gpu kernel adds the same numbers in a different order when tokens share a pass.
tags: LLM Inference, GPU, CUDA, llama.cpp
cover: /assets/img/batch-invariance-cover.png
---
qwen3-8b, greedy decoding, an rtx 5060 laptop with 8 gb. plain decoding wrote "`get(key)` to retrieve a value by key." speculative decoding, same model, same prompt, wrote "`get(key)` to retrieve a value" and went off into a different sentence.

out of 24 speculative runs, 8 matched plain decoding. the other 16 broke somewhere, and a rerun broke at the same byte every time.

[github.com/Cintu07/hiraishin](https://github.com/Cintu07/hiraishin) has the code, the patches and every log.

![fig. 1: one forward pass on this laptop, drawn to scale. the read of the weights is almost the whole cost, so a second token in the same pass is nearly free.](/assets/img/hiraishin/fig-01.png)

## why tokens share a pass

decoding one token streams every weight through the gpu. qwen3-8b at q4_k_m is 4.67 gb and this laptop moves about 286 gb/s, so a token can't cost less than 16.3 ms. a one token pass measured 19.1 ms. two tokens in the same pass took 19.5 ms. the weights were coming through anyway.

![fig. 2: a small model guesses ahead and the big model checks every guess in one pass. a guess is kept only if it equals what the big model picks on its own.](/assets/img/hiraishin/fig-02.png)

speculative decoding cashes that in. qwen3-0.6b guesses a few tokens, qwen3-8b checks them all in one pass, and a guess survives only if it equals the big model's own argmax at that position. every token that comes out is the big model's pick. the guarantee hangs on one condition: the big model's logits for a position inside a batch have to equal its logits for that position decoded alone.

## my first guess was wrong

llama.cpp's speculative example feeds the prompt as 49 tokens plus 1, while plain decoding feeds all 50 at once. different prompt processing, slightly different cache, so i blamed that first. i wrote my own test program that prefills both paths the same way and checks every output token against plain decoding.

it still broke in 16 of 24 runs.

the verify pass itself was computing different logits.

## floats care about order

near 100,000,000 the gap between neighbouring fp32 values is 8. so `(100000000 + 1) - 100000000` is 0 and `(100000000 - 100000000) + 1` is 1. same numbers, two answers.

![fig. 3: three numbers in two orders give two answers. a mat-vec splits each row's sum across warps, and the warp count changes with the number of tokens in the pass.](/assets/img/hiraishin/fig-03.png)

a transformer is mostly dot products, and a gpu never adds one up left to right. it deals the terms out to threads and warps and adds their partial sums at the end. deal them differently and the rounding changes. so the question was which kernels deal differently depending on how many tokens are in the pass.

## replay the answer

comparing generated text stops being useful at the first different token, because everything after it sees a different context. so i ran plain decoding, saved every token and the top logits at every position, then pushed that exact token sequence back through the model in batches of b and compared logits position by position. same inputs everywhere, only the batch shape changes. it's speculative decoding with a perfect drafter.

on stock kernels a batch of 2 already flipped the argmax at up to 4 positions per prompt. the logits moved by as much as 3.7, and the flips landed where plain decoding's top two were 0.008 to 0.28 apart. a coin flip, decided by rounding.

## the mat-vec kernel

decoding runs its matmuls through `mul_mat_vec_q`. take one row of a q6_k matrix with 4096 inputs: 16 weight blocks of 256. the activations are int8 in blocks of 32, and the inner products are `dp4a`, four int8 products summed into an int32. integer adds come out the same in any order. the floats show up when each block's integer result gets scaled and added into an fp32 accumulator.

a cuda block of `nwarps` warps walks the row:

```cpp
constexpr int blocks_per_iter = vdr * nwarps*warp_size / qi;
for (int kbx = tid / (qi/vdr); kbx < blocks_per_row_x; kbx += blocks_per_iter) {
    tmp[j][i] += vec_dot_q_cuda(vx, &y[j*stride_col_y + kby], kbx_offset + i*stride_row_x + kbx, kqs);
}
```

for q6_k, `blocks_per_iter` works out to `nwarps`. with 4 warps, warp 0 sums blocks 0, 4, 8 and 12. with 2 warps, it sums all eight even blocks. then the other warps hand their partials to warp 0 in a fixed order, and a 5 step xor shuffle folds the 32 lanes:

```cpp
for (int l = 0; l < nwarps-1; ++l) {
    tmp[j][i] += tmp_shared[l][j][i][threadIdx.x];
}
tmp[j][i] = warp_reduce_sum<warp_size>(tmp[j][i]);
```

`nwarps` comes from a table keyed by the number of columns, which here means the number of tokens. on this gpu it's 4 warps for 1 to 4 tokens and 2 warps for 5 to 8. past 5 to 7 tokens, k-quant weights leave this kernel for mmq, a tiled matmul with its own order of adds.

a batch of 5 groups the same row's blocks differently from a single token. same weights, different sum.

the single token kernel is the reference, so it stays untouched. batched launches borrow its geometry:

```cpp
static constexpr int calc_nwarps(ggml_type type, int ncols_dst, mmvq_parameter_table_id table_id,
                                 bool small_k = false, bool halve_iters = false, bool bi = false) {
    if (bi && ncols_dst > 1 && ncols_dst <= MMVQ_MAX_BATCH_SIZE) {
        return calc_nwarps(type, 1, table_id, small_k, halve_iters, false);
    }
    // ... the stock table
}
```

every column now walks the same blocks in the same order as a lone token and goes through the same reduction. batches stay on this kernel up to 16 tokens, and anything wider than 8 columns goes out in launches of at most 8. a column can't tell which launch it's in.

## attention

for one query llama.cpp runs a vector flash attention kernel. for more, it switches to a tensor core kernel that splits the work its own way. the fork i build on already had a `GGML_CUDA_BATCH_INVARIANT` switch that pins the vector kernel up to 8 queries, and i hoped it was the whole fix.

the replay said otherwise. on three of my four prompts, batches of 2 and 3 went bit-exact and batches of 5 and 9 still flipped. the warp table again: 2 and 3 tokens share the single token's 4 warps, 5 doesn't, and 9 queries also fell off the vector kernel. the mat-vec change plus an attention limit raised to 16 closed both.

## the bug that waited for position 384

the fourth prompt, a long rewrite, still had a top logit off by 0.338 at every batch size. no token flipped, so the text survived.

the guarantee didn't.

![fig. 4: llama.cpp rounds the attention range up to a multiple of 256 cells. a token inside a batch that crosses 256 attends over a different range than the same token decoded alone.](/assets/img/hiraishin/fig-04.png)

my first suspect was the kv padding. llama.cpp attends over the used cells rounded up to a multiple of 256, so a verify batch that crosses 256 sees a longer range than the same token decoded alone. i added a guard that stops every verify batch at a multiple of 256, and the difference stayed at exactly 0.338. i never saw the padding move a logit on its own.

![fig. 5: attention sums the kv cache in parallel blocks, and how many blocks comes from occupancy. a query whose last chunk holds real cells gets a different sum when that chunk joins another block.](/assets/img/hiraishin/fig-05.png)

the replay put the first difference at kv position 390. none of the other prompts got past 384.

the vector attention kernel walks the cache in 128 cell chunks across `P` parallel blocks. block `y` takes chunks `y`, `y + P`, `y + 2P`, keeps its own running max and sum, and a second kernel merges the partials. `P` starts from an occupancy query on whichever kernel is being launched:

```cpp
int max_blocks_per_sm = 1;
CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&max_blocks_per_sm, fattn_kernel,
    block_dim.x * block_dim.y * block_dim.z, nbytes_shared));
int parallel_blocks = max_blocks_per_sm;
```

the one query kernel and the two query kernel are different compiled kernels with different register counts, so they can fit a different number of blocks per sm and land on a different `P`.

with 512 cells there are 4 chunks. a query at 300 has nothing real in chunk 3: cells 384 to 511 are masked, and a fully masked chunk adds exact zeros wherever it lands. a query at 390 has real cells there. with `P = 4`, chunk 3 is its own partial. with `P = 3`, it gets added into block 0 after chunk 0. different order, different rounding, and only once the context passes 384.

a batched launch now sizes `P` from the one query kernel:

```cpp
fattn_kernel_t occupancy_kernel = nullptr;
if (cols_per_block > 1 && ggml_cuda_batch_invariant()) {
    occupancy_kernel = flash_attn_ext_vec<D, 1, type_K, type_V, use_logit_softcap>;
}
```

0.338 went to 0.000000. the 256 guard stayed in. it costs one shorter draft every 256 tokens.

## the receipts

replay, top logit difference: 0.000000 at batch sizes 2, 3, 5, 9 and 16 on the long prompt, and at 2, 3, 5, 8, 9 and 12 on two more prompts, for qwen3-8b at both q4_k_m and q6_k. end to end, 208 of 208 speculative runs came out identical to plain decoding. on 45 more prompts across code, math, explanations, summaries, structured output, creative writing and inputs up to 2,639 tokens, 45 of 45 were identical. plain decoding on the patched build matched plain decoding on the stock build on all 45, so the reference never moved.

tested on qwen3-8b, two quants, one gpu. that's the scope.

![fig. 6: the price of exactness. stock is cheap past 5 tokens because it switches to a faster kernel whose sums are not bit-identical to a single token.](/assets/img/hiraishin/fig-06.png)

## what exact costs

staying on the mat-vec at 9 tokens cost 3.33x a single token pass. stock pays 1.28x, with sums that don't match. my first idea was that the kernel re-decodes the 4 bit weights once per column, so i wrote one that unpacks each block once and reuses it across columns. it was slower, 3.05x at 8 tokens against 2.64x for the generic path. the compiled sass showed the compiler had already shared those loads.

the real cost was registers. the generic multi column kernel needed 108 per thread against 48 for one column, so far fewer warps fit on an sm to hide memory latency. moving runtime row checks out of my inner loop got my kernel past the generic path, and capping it at 128 registers, 4 blocks per sm with no spills, brought 9 tokens down to 1.96x. still bit-exact.

## so is it faster

yes. on the 45 prompts, plain decoding ran at 61.4 tok/s (the stock build measured 57.0 for plain decoding earlier in the same session, and i don't know why). stock speculative decoding with 8 guesses per cycle ran at 76.6 and got 37 of 45 outputs wrong. exact speculative decoding ran at 92.3 tok/s, 1.50x plain, with all 45 identical. the 92.3 also includes two speed fixes outside this post: the draft stops guessing when its top two logits are within 3 of each other, and the cuda graph cache keeps one recorded graph per batch size instead of re-recording on every change.

![fig. 7: one average speculative cycle on the 45 prompt eval against plain decoding, drawn to scale.](/assets/img/hiraishin/fig-07.png)

the 1.96x rarely comes up. the draft stops early, so the average verify batch is 2.97 tokens, and it takes 19.0 ms against 16.1 ms for a plain step. per cycle that's 8.5 ms of drafting, 19.0 ms of verifying, 0.4 ms of bookkeeping, and 2.52 tokens out. 77.3% of drafted tokens were accepted. 11.1 ms per token against 16.1 ms plain.

the order of the adds changed my output. the replay test is the part worth stealing: save plain decoding's tokens, push them back through in batches, diff the logits. it caught the 0.338 at position 390, which never changed a single word of output. next is the 1.96x, because the stock kernel verifies 9 tokens at 1.28x and i want that speed with the single token's order of adds.
