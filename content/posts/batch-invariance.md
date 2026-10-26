---
title: the same token gets a different answer when my gpu checks it in a batch
date: 2026-10-26
description: speculative decoding promises the exact output of the big model. on my laptop gpu it changed the text, because the big model's logits for a token depend on how many other tokens share the pass. the reasons, down to the warp and the attention block, and how each one was made bit-exact.
tags: LLM Inference, GPU, CUDA, llama.cpp
---
> speculative decoding promises the exact output of the big model. on my laptop it changed the text, because the model's logits for a token depend on how many other tokens ride in the same forward pass. this is why, down to the warp and the attention block, and how each cause was made bit-exact. code, patches and logs: [github.com/Cintu07/hiraishin](https://github.com/Cintu07/hiraishin).

qwen3-8b, greedy decoding, an rtx 5060 laptop gpu with 8 gb. plain decoding wrote "`get(key)` to retrieve a value by key." speculative decoding, same model, same prompt, wrote "`get(key)` to retrieve a value" and carried on with a different sentence. across my first 24 test runs the speculative output matched plain decoding 8 times. the other 16 drifted apart somewhere in the text, at the same byte every time i reran them.

speculative decoding is sold as lossless, and the rule it uses is. the gpu math under it isn't. this post follows one token through the kernels that compute its logits and finds the places where the answer depends on how many tokens are in the pass. then it fixes each one until the logits match to the last bit.

![fig. 1: one forward pass on this laptop, drawn to scale. the read of the weights is almost the whole cost, so a second token in the same pass is nearly free.](/assets/img/hiraishin/fig-01.png)

first, why tokens share a pass at all. decoding one token means streaming every weight of the model through the gpu once. for qwen3-8b at q4_k_m that's 4.67 gb, and this laptop moves about 286 gb/s, so a token costs at least 16.3 ms no matter how little math it needs. the measured pass with one token is 19.1 ms. with two tokens in the same pass it's 19.5 ms. the weights were coming through anyway.

![fig. 2: a small model guesses ahead and the big model checks every guess in one pass. a guess is kept only if it equals what the big model picks on its own.](/assets/img/hiraishin/fig-02.png)

speculative decoding cashes that in. a small draft model, qwen3-0.6b, guesses a few tokens. the big model runs all of them in one batched pass and at each position takes its own argmax. a guess survives only if it equals that argmax. so every token that comes out is, by construction, the big model's own choice for that position. the proof of losslessness rests on one sentence nobody says out loud: the big model's logits for position 5 inside a batch must equal its logits for position 5 decoded alone. that sentence is false on this gpu, and the rest of this post is why.

to see why, start with something smaller than a gpu. fp32 addition isn't associative. a float has 24 bits of mantissa, so around 100,000,000 the next representable value is 8 away. (100000000 + 1) - 100000000 gives 0, because the 1 is rounded away when it meets the big number first. (100000000 - 100000000) + 1 gives 1. same three numbers, different order, different answer. every dot product in a transformer is a long sum of products, and a gpu never adds them left to right. it hands pieces of the sum to different threads and combines the partial sums later. whoever decides how the work is split decides the order of additions, and the order decides the rounding.

![fig. 3: three numbers in two orders give two answers. a mat-vec splits each row's sum across warps, and the warp count changes with the number of tokens in the pass.](/assets/img/hiraishin/fig-03.png)

the first place this bites is the matrix-vector kernel llama.cpp uses for decoding, `mul_mat_vec_q`. take one row of a q6_k weight matrix with 4096 inputs. q6_k packs weights in blocks of 256, so the row is 16 blocks. the activations get quantized to 8 bit in blocks of 32. inside a block everything is integer: `dp4a` multiplies four int8 pairs and adds them into an int32, and integer addition is exact in any order. floats enter at the edges, when each block's integer dot product is scaled by the block's fp16 scales and added into a running fp32 sum.

each row is handled by a cuda block of `nwarps` warps, 32 lanes each. each thread walks the row in steps:

```cpp
constexpr int blocks_per_iter = vdr * nwarps*warp_size / qi;
for (int kbx = tid / (qi/vdr); kbx < blocks_per_row_x; kbx += blocks_per_iter) {
    tmp[j][i] += vec_dot_q_cuda(vx, &y[j*stride_col_y + kby], kbx_offset + i*stride_row_x + kbx, kqs);
}
```

for q6_k, `qi` is 32 and `vdr` is 1, so one warp covers one 256 weight block per step and `blocks_per_iter` equals `nwarps`. with 4 warps, warp 0 sums blocks 0, 4, 8 and 12, warp 1 sums 1, 5, 9 and 13, and so on. with 2 warps, warp 0 sums all eight even blocks. after the loop, warps 1 and up write their partials to shared memory, warp 0 adds them in order, and a 5 step xor shuffle folds the 32 lanes into one number.

```cpp
for (int l = 0; l < nwarps-1; ++l) {
    tmp[j][i] += tmp_shared[l][j][i][threadIdx.x];
}
tmp[j][i] = warp_reduce_sum<warp_size>(tmp[j][i]);
```

every piece of that order follows `nwarps`. and `nwarps` comes from a table keyed by the number of columns, meaning tokens in the pass. on this gpu the table says 4 warps for 1 to 4 tokens and 2 warps for 5 to 8. a batch of 5 groups the same row's blocks differently from a single token and rounds differently. past 5 to 7 tokens, k-quant weights leave this kernel entirely for a tiled matmul (mmq) built for throughput, whose accumulation order has nothing to do with the single token kernel.

the fix keeps the single token kernel exactly as it is, since its output is the reference, and makes every multi token launch inherit its geometry:

```cpp
static constexpr int calc_nwarps(ggml_type type, int ncols_dst, mmvq_parameter_table_id table_id,
                                 bool small_k = false, bool halve_iters = false, bool bi = false) {
    if (bi && ncols_dst > 1 && ncols_dst <= MMVQ_MAX_BATCH_SIZE) {
        return calc_nwarps(type, 1, table_id, small_k, halve_iters, false);
    }
    // ... the stock table
}
```

with the same `nwarps`, every column walks the same blocks in the same order and goes through the same reduction. the number of rows a cuda block handles can still differ, because rows never mix. under the same switch the batch stays on this kernel up to 16 tokens instead of moving to mmq, and more than 8 columns are split into launches of at most 8, since a column's arithmetic doesn't care which launch it lands in.

attention is the second place. for one query llama.cpp runs a vector flash attention kernel. for several queries it switches to a tensor core kernel that tiles the work its own way. the fork i build on already ships a switch, `GGML_CUDA_BATCH_INVARIANT`, that keeps the vector kernel for up to 8 queries. i raised that to 16 so a batch of 9 stays on it too.

that switch already made a measurable difference before any of my changes. to measure, i ran plain decoding, kept every token and the top logits at every position, then fed that exact sequence back through the model in batches of b tokens and compared each position's logits with the single token run. this replay is speculative decoding with a perfect drafter, so any difference it finds is a difference the real loop would hit. with stock kernels, batches of 2 already flipped the argmax at up to 4 positions per prompt, wherever plain decoding's top two logits were close: margins of 0.008 to 0.28, while the batched logits moved by up to 3.7. with the fork's switch on, batches of 2 and 3 matched bit for bit on three of my four prompts, and batches of 5 and 9 still flipped. the warp table explains that split, since 2 and 3 tokens share the single token's 4 warps and 5 or more don't, and 9 also fell off the vector attention kernel. the matmul fix plus the higher attention limit closed 5 and 9. what was left had nothing to do with which kernel ran.

![fig. 4: llama.cpp rounds the attention range up to a multiple of 256 cells. a token inside a batch that crosses 256 attends over a different range than the same token decoded alone.](/assets/img/hiraishin/fig-04.png)

the next suspect sits in the kv cache, not a kernel. llama.cpp doesn't attend over exactly the cells in use. `get_n_kv` rounds up:

```cpp
const uint32_t n_pad_cur = std::max(n_pad, 256u);
result = std::max(std::min(cells.size(), std::max(n_pad_cur, GGML_PAD(cells.used_max_p1(), n_pad_cur))), result);
```

decode token 255 alone and the highest used cell is 255, so attention sees 256 cells. put token 255 in a verify batch that spans 254 to 257 and the highest used cell is 257, so every query in that batch sees 512 cells. the extra cells are masked to minus infinity, so they contribute exactly zero after the exponential. the length of the range does change one thing: how many parallel blocks attention splits it across, which is exactly the mechanism behind the last bug below. as far as i can reason it through, the extra chunks are always empty for these queries, and adding exact zeros in a different place can't change a sum. i never measured this one in isolation. i found it reading the code and guarded it before i could.

the guard needs no gpu code. a verify batch is never allowed to cross a multiple of 256. if a draft would cross, it gets cut so the batch ends at 255 and the next one starts at 256. it costs one shorter draft every 256 tokens, and the batch and the single token always see the same range, so there's nothing left to reason about.

![fig. 5: attention sums the kv cache in parallel blocks, and how many blocks comes from occupancy. a query whose last chunk holds real cells gets a different sum when that chunk joins another block.](/assets/img/hiraishin/fig-05.png)

with the matmul fix, the attention limit and the guard in place, three of my four prompts were bit-exact at every batch size. the fourth, a long rewrite prompt, still showed a logit difference of 0.338 at every batch size from 2 up. no argmax flipped, so the text happened to survive, but a guarantee that holds by luck isn't one. the replay pinned the first difference to one place, kv position 390. the other prompts never got past 384.

the vector attention kernel walks the kv cache in chunks of 128 cells. it splits them across `P` parallel cuda blocks, block `y` taking chunks `y`, `y + P`, `y + 2P` and so on, each block keeping its own running max and sum, and a final kernel merges the `P` partials. `P` is chosen at launch:

```cpp
int max_blocks_per_sm = 1;
CUDA_CHECK(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&max_blocks_per_sm, fattn_kernel,
    block_dim.x * block_dim.y * block_dim.z, nbytes_shared));
int parallel_blocks = max_blocks_per_sm;
```

then a short search over wave efficiency, capped by the number of chunks. the starting point is the occupancy of the kernel being launched. the one query kernel and the two query kernel are different compiled kernels with different register counts, so they can fit a different number of blocks per sm, and they can land on a different `P`.

look at what `P` does to one query. with 512 cells there are 4 chunks. a query at position 300 has real cells only in chunks 0, 1 and 2. chunk 3 is fully masked and contributes exactly zero to any partial it joins, so whether chunk 3 gets its own block or gets folded into block 0's running sum, the merged result is identical. a query at position 390 has real cells in chunk 3. if `P` is 4, chunk 3 is its own partial. if `P` is 3, chunk 3 is added into block 0 after chunk 0, which is a different order of additions, so a different rounding. that's why the bug waited for position 384. below it, the chunk that moves around is empty.

the fix tells a batched launch to size `P` from the one query kernel's occupancy:

```cpp
fattn_kernel_t occupancy_kernel = nullptr;
if (cols_per_block > 1 && ggml_cuda_batch_invariant()) {
    occupancy_kernel = flash_attn_ext_vec<D, 1, type_K, type_V, use_logit_softcap>;
}
```

the batch-invariant path also already sized the wave search as if for a single query tile, so with this every query splits its kv range the way it would alone.

with that, the replay came back clean. top-1 logit difference 0.000000 for batches of 2, 3, 5, 9 and 16 on the prompt that had found the occupancy bug, and for batches of 2, 3, 5, 8, 9 and 12 on two prompts with qwen3-8b at both q4_k_m and q6_k. end to end, 208 of 208 speculative runs matched plain decoding token for token. on a separate 45 prompt set across code, math, explanations, summaries, structured output, creative writing and long documents up to 2,639 tokens of input, 45 of 45 matched. plain decoding from the patched build also matched plain decoding from the stock build on all 45. that last check matters. a fix could make batched and single token decoding agree by changing both, which would make the output consistent and still different from the model you started with. keeping the single token path untouched means the reference never moved.

![fig. 6: the price of exactness. stock is cheap past 5 tokens because it switches to a faster kernel whose sums are not bit-identical to a single token.](/assets/img/hiraishin/fig-06.png)

this isn't free. staying on the mat-vec at 9 tokens instead of switching to mmq cost 3.33x a single token pass, where stock pays 1.28x for an inexact answer. most of that was occupancy again. the multi column kernel used up to 168 registers per thread against 48 for one column, so far fewer warps fit on each sm to hide memory latency. a dedicated q4_k and q6_k kernel that calls the same per column dot product functions, shares weight unpacking across rows, and asks the compiler for 4 blocks per sm (128 registers, no spills) brings 9 tokens down to 1.96x, still bit-exact.

the two mechanisms here, summation order set by a launch geometry that depends on batch size and summation order set by occupancy, aren't special to speculative decoding. any engine that picks kernels and work splits by shape can have them. the occupancy one is the nastier of the two, because it sleeps until the context crosses a chunk boundary that short test prompts never reach.
