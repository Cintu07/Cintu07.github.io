---
title: reordering 2-bit numbers until a 27b model got 3.8x faster on a laptop cpu
date: 2026-10-17
description: a 27b ternary model on a snapdragon x cpu, no gpu. prompts get read 3.8x faster and answers get written 1.5x faster, with the same output. how the kernel works, with the code.
tags: C, SIMD, ARM, Inference, Quantization
cover: /assets/img/ciot-t2p-cover.png
---
> a 27b model on a snapdragon x laptop cpu, no gpu. prompts get read 3.8x faster and answers get written 1.5x faster, and the output matched the official kernel on everything i checked. this is how i wrote the kernel. code: [kernels/t2p.c](https://github.com/Cintu07/ciot/blob/main/kernels/t2p.c), repo: [@Cintu07/ciot](https://github.com/Cintu07/ciot).

ok so. i run a 27 billion parameter model on my laptop's cpu. the official runtime gets 6.5 tokens a second out of it. when i did the math on what the memory could deliver, the answer was about 15.

that's a big gap, and the cpu was spending it on unpacking. the weights are squeezed tiny to save space, and before the cpu can multiply anything it has to un-squeeze them. the unpacking costs more than the multiplying.

so i changed where the bits sit in the file. prompt reading went from 8.4 to 31.7 tokens a second and answer writing went from 6.5 to 9.7. same output as stock on every check i ran.

this post is how i got there, including a detour that looked brilliant and lost. you don't need to know simd. i'll explain things as they come up. the notes at the bottom list everything i didn't test.

## what's running

the model is ternary bonsai 2 27b from prismml. ternary means every weight is one of three values: -1, 0 or +1. no decimals. the file i use (`pq2_0`) stores each weight in 2 bits, so four fit in a byte, plus one fp16 scale for every 128 weights. 7.21 gb for the whole model.

2 bits can hold four values and i only need three, so the file stores `u = w + 1`. that's 0, 1 or 2, no negative numbers to worry about.

the machine is a snapdragon x x126100 laptop. 8 cores, 16 gb, windows, no gpu. the runtime is prismml's fork of llama.cpp.

two words you'll see a lot. *prefill* is the model reading your prompt. *decode* is the model writing its answer one token at a time. they stress the cpu in different ways, and that's most of this post.

## the ceiling

before i write any code i write down the number i can't beat.

writing one token means touching every weight in the model once. so the speed limit is how fast memory can hand weights to the cpu. it's like reading a 7 gb book out loud. you can't go faster than the pages turn.

i measured it with a dumb loop that sums a 1 gb buffer. one thread reads about 60 gb/s. four threads and up reach 100 to 115 gb/s, and that's the wall.

about 6.9 gb of weights get streamed per token (the 340 mb embedding table is a lookup, so it stays out). 6.9 gb at 110 gb/s is about 62 ms, so roughly 15 tokens a second.

the official runtime does 6.5. that's 154 ms a token, with the memory only about 40% busy.

so the time between 6.5 and 15 goes to something other than memory. i wanted to know what.

## the paperwork

here's the job. the numbers flowing through the model (activations) get squashed to int8 on the fly. the weights are ternary. multiplying them is the whole point, and arm has one instruction made for it, `sdot`. it takes 16 int8 values and 16 more, multiplies them pairwise, and adds them up in groups of four.

`sdot` wants its 16 values side by side, one per byte. but the weights are packed four to a byte. so something has to unpack them first. this is how the official kernel does it for 16 weights, trimmed from `ggml_vec_dot_pq2_0_q8_K`:

```c
const int8x16_t qv0 = vsubq_s8(
    vreinterpretq_s8_u8(vandq_u8(vshlq_u8(ggml_vqtbl1q_u8(raw16, idx_lo), shifts), mask2)), one);
acc = ggml_vdotq_s32(acc, qv0, y0);
```

read it from the inside out. a table lookup spreads the packed bytes into the right lanes. a shift lines up each lane's 2-bit pair. a mask throws away the rest. a subtract takes off the +1 from storage. then one `sdot`.

![for every 16 weights the stock kernel does four chores before the one real job. mine does one chore.](/assets/img/ciot-t2p-paperwork.png)

per 64 weights that's 16 chores and 4 real instructions. the multiplying is the smallest part of the cpu's day. the dot is the job and the other four are a meeting about the job.

so a faster file format won't help unless it also cuts the chores. that's the question for the rest of the post.

## the detour that lost

the model also ships as a 1.75-bit file (`ptq1_0`). it packs five weights per byte, because 3^5 is 243 and that fits in 256. the file is 18% smaller than the 2-bit one. on a machine limited by memory, smaller should win. right?

at the commit i measured (prism 6bfcd79) the official runtime ran that file through a plain c loop on arm. so i wrote a neon kernel for it. a neon kernel for that format landed upstream a few days later (prism #290), so the first bar in the chart further down is a snapshot of the older commit.

getting one weight out of a base-3 byte is arithmetic. weight `k` of byte `b` is `floor(3 * (b * 3^k mod 256) / 256)`. that floor turns out to equal how many of two thresholds the number crosses: `(v >= 86) + (v >= 171)`. neon compares return all ones for true, which reads as -1, so you subtract them:

```c
// v already holds byte * 3^nn (mod 256); returns the 16 weights in {-1, 0, +1}.
static inline int8x16_t ptq1_0_trits(uint8x16_t v) {
    const int8x16_t ge1 = vreinterpretq_s8_u8(vcgeq_u8(v, vdupq_n_u8(86)));
    const int8x16_t ge2 = vreinterpretq_s8_u8(vcgeq_u8(v, vdupq_n_u8(171)));
    return vsubq_s8(vsubq_s8(vdupq_n_s8(-1), ge1), ge2);
}
```

i checked that identity against all 256 byte values, because i like feeling safe.

it worked. 124.7 gigaweights a second on 8 threads, up from 19.6 for the plain loop. six times faster. and then i ran the official 2-bit kernel on the bigger file and it did 231.6. mine was reading 27 gb/s out of a bus that gives 110. it spent its whole life unpacking.

cute trick. cute lost. a smaller file only wins if the cpu has spare instructions to unpack it, and this one didn't.

## the layout

back to 2 bits, with one question. if i can store the bits anywhere i want, where do i put them so that unpacking costs one instruction?

here's how i think about it. a byte is a lunchbox with four compartments. the cpu opens 16 lunchboxes at once and wants compartment 1 from every box, as 16 separate numbers. so which 16 weights should sit in compartment 1 across those boxes? the 16 i want to multiply together. then one `and` pulls them all out.

![one 16-byte word. bytes 0 to 7 are row a and bytes 8 to 15 are row b. take one slot from all 16 bytes and you get what the matrix instruction wants.](/assets/img/ciot-t2p-layout.png)

the details. a block is 4 rows by 128 weights in 136 bytes: four fp16 scales and 128 code bytes. that's the same size as four stock blocks, so the file doesn't grow. the 128 code bytes are eight words of 16 bytes, in two row pairs. inside a word, bytes 0 to 7 belong to one row and bytes 8 to 15 to the next. each byte holds four weights of its row, eight apart.

why eight apart, and why two rows glued together? that's the prefill section. for now look at one compartment across the whole word. it's 8 weights of row a, then the same 8 weights of row b.

the packer is short:

```c
void ciot_t2p_pack(const int8_t* w[4], const float scale[4], ciot_block_t2p* out) {
    for (int r = 0; r < 4; ++r) out->d[r] = f32_to_fp16(scale[r]);
    for (int p = 0; p < 2; ++p) {
        for (int wd = 0; wd < 4; ++wd) {
            for (int j = 0; j < 16; ++j) {
                const int row = 2 * p + (j >= 8);
                uint8_t byte = 0;
                for (int s = 0; s < 4; ++s) {
                    const int k = 8 * (4 * wd + s) + (j & 7);
                    byte |= (uint8_t) ((w[row][k] + 1) << (2 * s));
                }
                out->qs[p][wd][j] = byte;
            }
        }
    }
}
```

it runs once when the model loads, as an in-place repack of the tensors. after that it costs nothing per token.

## the trick with 4 and 16

this is the part i like.

to pull compartment 1 out of a byte the textbook way you shift right by 2 and mask with 3. but look at what a mask alone gives you. `and` with `0x0c` leaves the value sitting two bits up, so you get `u * 4`. `and` with `0x30` leaves `u * 16`. no shift at all, the numbers are just bigger. and `sdot` doesn't care. it multiplies and adds whatever int8s it's handed.

so those dot products come out 4x and 16x too big. fine. keep each slot in its own accumulator and fix the scale once per block instead of once per vector. slot 3 is the one exception. `u = 2` sitting at bit 6 would be 128, which `sdot` reads as -128, so that slot gets a real shift.

```c
#define T2P_SLOT0(v) vreinterpretq_s8_u8(vandq_u8((v), vdupq_n_u8(0x03)))
#define T2P_SLOT1(v) vreinterpretq_s8_u8(vandq_u8((v), vdupq_n_u8(0x0C)))
#define T2P_SLOT2(v) vreinterpretq_s8_u8(vandq_u8((v), vdupq_n_u8(0x30)))
#define T2P_SLOT3(v) vreinterpretq_s8_u8(vshrq_n_u8((v), 6))
```

three ands and one shift for a 16-byte word. the stock path spent sixteen instructions on the same 64 weights. here's the decode loop for one block, straight from the file:

```c
for (int wd = 0; wd < 4; ++wd) {
    const int8x16_t y0 = dup8(q8 + 8 * (4 * wd + 0));
    const int8x16_t y1 = dup8(q8 + 8 * (4 * wd + 1));
    const int8x16_t y2 = dup8(q8 + 8 * (4 * wd + 2));
    const int8x16_t y3 = dup8(q8 + 8 * (4 * wd + 3));
    for (int p = 0; p < 2; ++p) {
        const uint8x16_t v = vld1q_u8(x[i].qs[p][wd]);
        a[p][0] = vdotq_s32(a[p][0], T2P_SLOT0(v), y0);
        a[p][1] = vdotq_s32(a[p][1], T2P_SLOT1(v), y1);
        a[p][2] = vdotq_s32(a[p][2], T2P_SLOT2(v), y2);
        a[p][3] = vdotq_s32(a[p][3], T2P_SLOT3(v), y3);
    }
}
```

`dup8` copies 8 activation bytes into both halves of a vector, so one `sdot` serves both rows of the pair. lanes 0 and 1 collect row `2p`, lanes 2 and 3 collect row `2p+1`. that's eight accumulators running independently, so each dot's latency hides behind the others.

then once per 128 weights i fix the scales. call the four accumulators `a0` to `a3`. `a1` is 4x too big and `a2` is 16x too big, so:

```
a2 + 4*a1 + 16*(a0 + a3) = 16 * dot(u, y)
```

and since `u = w + 1`, we have `dot(w, y) = dot(u, y) - sum(y)`. subtract `16 * sum(y)` and the +1 is gone. getting `sum(y)` costs almost nothing, because the activation block already carries partial sums of 16 values each, so the sum over 128 is one add across 8 shorts. the leftover 1/16 goes into the float scale that gets multiplied in anyway.

```c
const int32x4_t t0 = vmlaq_n_s32(vmlaq_n_s32(a[0][2], a[0][1], 4), vaddq_s32(a[0][0], a[0][3]), 16);
const int32x4_t t1 = vmlaq_n_s32(vmlaq_n_s32(a[1][2], a[1][1], 4), vaddq_s32(a[1][0], a[1][3]), 16);
// [row0, row1, row2, row3], each 16 * (u . y); subtracting 16 * sum(y) turns u back into w
const int32x4_t tot = vsubq_s32(vpaddq_s32(t0, t1), vdupq_n_s32(16 * ysum));
```

overflow? a block is 128 products of at most 2 * 127, times 16. that's 520,192, and int32 has room. everything stays exact integer math until the final float conversion.

## did it reach the wall?

the test is a 32768 by 8192 matvec. that's 268 million weights, 71 mb, far bigger than any cache, on a persistent pool of 8 threads.

![how fast each kernel reads weights, in gb per second. the dashed line is the memory limit.](/assets/img/ciot-t2p-wall.png)

| kernel (8 threads, 32768 x 8192 matvec) | gweights/s | gb/s of weights |
|---|---|---|
| official, 1.75-bit file, plain c loop (prism 6bfcd79) | 19.6 | 4.3 |
| my base-3 neon kernel, 1.75-bit file | 124.7 | 27.3 |
| official, 2-bit file, neon kernel | 231.6 | 61.5 |
| ciot 2-bit layout, first version | 390.5 | 103.7 |

the row-pair layout from the picture above does 107.0 in its own run, with the first 2-bit layout at 100.6 in that same run. that's 6%, and i changed the accumulator scheme in the same edit, so i can't give the layout the credit. it was never meant for decode anyway. keep reading.

either way the kernel sits within about 7% of what the memory can physically do. decode should be near 15 tokens a second. it's 9.7.

so the kernel is done and the gap sits above it. when i replayed the 401 real matvecs of one token outside the runtime they took about 70 ms. inside the runtime the same matmuls took 92 ms, and another 19 ms went to copying recurrent state, because this model is a hybrid with a running state in most of its layers. that's plumbing, and it's what i'm taking apart next.

## prefill wants a different shape

decode multiplies the weights by one activation column. each weight gets loaded and used once, so the bus is the limit and the last section was the whole story.

prefill flips that. with 64 prompt tokens in flight, a weight you've loaded can be used 64 times. the bus stops mattering and instruction count takes over. enter `smmla`. it multiplies a 2 by 8 int8 matrix by an 8 by 2 int8 matrix into a 2 by 2 tile. that's 32 multiply-adds in one instruction, double what `sdot` does, and every operand gets reused in both directions.

the activation side came free. q8_k has a four-column variant with the columns interleaved in 8-byte chunks, which is already the shape `smmla` wants on the right.

the weight side is why the layout looks the way it does. my first layout had 16 consecutive weights of one row per slot. fine for `sdot`, but `smmla` wants two rows by eight, so every vector needed two zips to weave a row with its neighbour first. zips do no arithmetic. they're pure toll.

row pairs move the toll into the file. a decoded slot is already `[row a: 8 weights | row b: the same 8]`, so there's nothing to zip. this is the multiply, from the file:

```c
#define T2P_MM(acc_, slot_, c_)                                                    \
    {                                                                              \
        const int8x16_t b01 = vld1q_s8(qc0 + 32 * (c_)), b23 = vld1q_s8(qc0 + 32 * (c_) + 16); \
        const int8x16_t w0 = slot_(v0), w1 = slot_(v1);                            \
        acc_[0][0] = vmmlaq_s32(acc_[0][0], w0, b01);                              \
        acc_[0][1] = vmmlaq_s32(acc_[0][1], w0, b23);                              \
        acc_[1][0] = vmmlaq_s32(acc_[1][0], w1, b01);                              \
        acc_[1][1] = vmmlaq_s32(acc_[1][1], w1, b23);                              \
    }
```

one decoded slot per row pair, two activation operands, four `smmla`, every operand used twice. on 17408 by 5120 weights with 8 threads the 4-token tile went from 862 to 1136 gmac/s and the 64-token tile went from 850 to 1076. bit-identical to the first layout, just faster.

and one layout serves both instructions. the `dup8` trick from the decode loop gets the same row pairs working with `sdot`.

## the leftovers

the matrix kernel works on groups of four activation columns. a 64-token prompt is sixteen clean groups. but a batch of 2 or 3 tokens leaves a remainder, and the runtime handled each leftover row with its own matvec call. every one of those streams all 7 gb of weights again.

this matters for speculative decoding, where the model checks a few guessed tokens in one batch. a batch of 3 lands exactly in the gap. the fix pads the leftover rows with zeros up to a full tile, does one `smmla` pass, and copies out only the real outputs. a single leftover row still takes the `sdot` path.

on a code-editing prompt, with a prompt-lookup guesser and rollback of the recurrent state, decode went from 8.9 to 14.1 tokens a second over 306 tokens. 76% of the guesses were accepted and not one token differed from plain greedy. that speculation code is separate research and lives outside the repack patch, so read that number as its own result.

## did i break the model?

a faster wrong answer is a bug, so three checks.

first, an integer oracle. i feed the repacked buffer integer activations and compare against a dumb scalar loop, exactly, no tolerance. 78 cases: batch widths 1 to 5, 7 and 8, row counts 4, 8 and 12, inner sizes 256, 512 and 1024, shapes the selector should reject, all zeros, constants, extreme values.

second, perplexity on the real 27b. three chunks of 128 tokens, 10.5976, 17.2967 and 16.5409, identical on stock and patched.

third, greedy tokens on three prompts through the native api. the ids match (32, 28 and 25 tokens, and two prompts stopped at end of generation).

what this doesn't prove: the integer sums are exact, but the float math around them can round differently, and "same at printed precision" is weaker than "same bits". it says the model acts like the same model on everything i checked. i wouldn't promise more.

## stuff that went wrong

my test was wrong. the first oracle run failed 24 cases, all with inner size 512 or 1024. the kernel was fine. my test only forced an absolute max of 127 in the first 256 values of each column, so later blocks could land on a quantization scale other than 1, the conversion stopped being exact, and my exact comparison failed for the wrong reason. the other bug the validation found was a missing link flag in a tool, hidden by an x64 build that used dlls. both were bugs in my tests. i'd put that on a plaque if i weren't worried about what the tests are still missing.

windows ate a third of every token. this was the 1.75-bit file with my first kernel. a profile said the matmuls were only 65% of a token and the rest was about 2,400 tiny operations at around 100 microseconds each. the cause is a barrier. the runtime spins 8 workers, the os pauses one for a moment, and the other seven wait, because that's what a barrier is. one thread takes a nap and everyone takes a nap. high priority took decode from 3.8 to 6.0 tokens a second on the same binary and made the matmuls 89% of the token.

my benchmark measured thread creation. the first version spawned fresh threads in every iteration and reported 282 gigaweights a second for the first 2-bit layout. with a persistent pool it's 391. a benchmark that spawns threads in its loop is a thread spawning benchmark.

memory mapping cost 21 ms a token. with the default memory-mapped load, the embedding lookup alone took about 21 ms per token. page faults, as far as i can tell, with the mapped file sitting next to the repacked copy. i didn't dig further. loading without mmap made it disappear.

## the numbers

two sets of runs, and they differ on purpose. the first is my research build, 8 threads, high priority, two rounds of `llama-bench` on the 2-bit file. the stock rounds come from one session and the row-pair rounds from a later one with the same settings, so read the ratio as approximate.

| | prefill (pp64) | decode (tg32) |
|---|---|---|
| stock, round 1 and 2 | 8.78 and 8.04 tok/s | 7.08 and 5.98 tok/s |
| ciot, round 1 and 2 | 32.34 and 31.12 tok/s | 9.81 and 9.51 tok/s |
| mean ratio | 3.8x | 1.5x |

the second is the clean patch alone, the one-file change i'd propose upstream, built next to a stock build from the same commit. 4 threads, high priority, two interleaved rounds:

| | prefill (pp64) | decode (tg32) | perplexity pass |
|---|---|---|---|
| stock | 4.87 tok/s | 4.17 tok/s | 27.52 s |
| patched | 18.27 tok/s | 6.63 tok/s | 7.44 s |
| ratio | 3.76x | 1.59x | 3.7x |

four threads is slower in absolute terms and the ratios hold. standard deviations on those rounds were 0.21 tok/s or less.

## what's next

the kernel streams within about 7% of what the memory can do. the model writes at 9.7 tokens a second against a ceiling near 15, and the gap between those is runtime plumbing. that's next.

## notes

- **one machine.** everything here ran on one snapdragon x x126100 laptop. that it carries over to other arm cores is a hypothesis.
- **only the `smmla` path ran.** the repack has a fallback for cores with `sdot` but no `smmla`. it compiles and passes a syntax check for that target, but i have never executed it. this cpu has both instructions.
- **the validation runs were on battery.** the clean-patch runs started at 38% and 32% charge. stock and patched were interleaved under the same conditions so the ratios are fair, but the absolute numbers are probably lower than they'd be on the charger.
- **the idea has precedent.** ggml already repacks several formats (q4_0 and q8_0 among them) into interleaved tiles for `sdot` and `smmla`. what's specific here is the in-place slot masking with the factor-of-16 recombination, and the row-pair layout for this 2-bit format.
- **the model belongs to its authors.** the weights and the file format come from them. my part is the kernel and the repack.
- **the official runtime keeps moving.** the research numbers use prism 6bfcd79 and the clean-patch validation uses e8fd209. a neon kernel for the 1.75-bit file landed upstream in between, so re-measure before comparing against a current build.
- **decode sits below its ceiling.** 9.7 tok/s end to end against about 15 for the kernel alone.
- **reproduce it.** the clean patch is [patches/pr-arm-pq2_0-repack.patch](https://github.com/Cintu07/ciot/blob/main/patches/pr-arm-pq2_0-repack.patch). on an arm64 windows machine with clang and ninja on the path and the pq2_0 files in `models/`, `tools/validate_arm_contribution.ps1 -Stage Small` and `-Stage Large` build stock and patched side by side and run every check above. raw outputs are in `bench/contribution/`.
