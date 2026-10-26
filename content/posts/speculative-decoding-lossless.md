---
title: speculative decoding is lossless. my gpu disagreed.
date: 2026-10-26
description: stock speculative decoding changed the output of an 8b model on my laptop. four bugs later it runs at 92 tok/s on a 45 prompt eval, 1.5x plain decoding, with every output identical token for token.
tags: LLM Inference, GPU, CUDA, llama.cpp
---
> speculative decoding is supposed to be free speed with zero quality loss. on my 8 gb laptop gpu it changed the output on 3 of my first 4 test prompts. this is where that came from, the four bugs behind it, and what it took to make it exact: 92 tok/s on a 45 prompt eval, 1.5x plain decoding, every output identical to plain decoding token for token. code, patches and every log are at [github.com/Cintu07/hiraishin](https://github.com/Cintu07/hiraishin).

i wanted an 8b model to talk faster on my laptop than its memory should allow. the plan was speculative decoding, the trick everyone describes as free speed with zero quality loss. so before building anything i measured the stock version, and the first number that came back had nothing to do with speed. on 3 of my 4 test prompts the output changed.

same model, same prompt, greedy decoding, and the text forked halfway through a sentence. plain decoding wrote "`get(key)` to retrieve a value by key." the speculative run wrote "`get(key)` to retrieve a value" and moved on. tiny difference. it means the guarantee is gone.

this post is about where that difference comes from, the four separate bugs behind it, and what it took to make speculative decoding exact on an rtx 5060 laptop gpu with 8 gb of memory. it ends at 92 tok/s on a 45 prompt eval, 1.5x plain decoding, with every output identical to plain decoding token for token. you don't need to know cuda to follow it. you need to be ok with arithmetic.

some words i'll use a lot. a **token** is a chunk of text, roughly three quarters of a word. the model outputs a **logit** for every token in its vocabulary, 151,936 of them for qwen3, and **greedy** decoding picks the biggest one, the **argmax**. a **kernel** is one function running on the gpu, a **warp** is a group of 32 gpu threads that run in lockstep, and the **kv cache** is where the model keeps what it already read.

## the bus is the speed limit

start with what one decoding step costs. to produce one token, an 8b model multiplies the current hidden state through every weight matrix it has. qwen3-8b at q4_k_m keeps 4.67 gb of weights on the gpu, and every one of those bytes has to travel from memory into the compute units once per token.

the math is small. about two operations per weight, so 16 billion for a token. the gpu could chew through that in a fraction of the time it spends waiting for the bytes to show up. my laptop's memory delivers about 286 gb/s in practice. 4.67 gb at 286 gb/s is 16.3 ms. so one token costs at least 16.3 ms, and plain decoding tops out around 61 tok/s. the measured number is 61.4.

![fig. 01: one forward pass, drawn to scale. reading the weights is the whole cost, a second token in the same pass adds 2%.](/assets/img/hiraishin/fig-01.png)

look at the second bar in fig. 01. a forward pass with one token in it takes 19.1 ms in this measurement (it returns every logit, which adds a copy). the same pass with two tokens takes 19.5 ms. the second token costs 0.4 ms, 2% more, because the weights were already flowing through and the math for one more token barely registers.

that's the loophole. reading the weights is what you pay for. once they're in flight, extra tokens ride along almost for free.

## the loophole: guess, then check in bulk

the problem with exploiting it is that generation is sequential. token 2 depends on token 1, so you can't just compute 5 tokens in one pass. you don't know them yet.

speculative decoding gets around this by guessing. a small draft model, here qwen3-0.6b with 14x fewer parameters, guesses the next few tokens one at a time. that's cheap, about 3.6 ms per guess. then the big model, the target, takes all the guesses in one batched pass and scores every position at once.

![fig. 02: the draft model guesses, the target checks every guess in one pass and keeps the ones it agrees with.](/assets/img/hiraishin/fig-02.png)

the accept rule is simple. walk the guesses left to right. at each position, compare the guess with the target's own argmax for that position. if they match, keep the guess and move on. at the first mismatch, throw away the rest and take the target's own token instead. you always get at least one token per cycle, and every token you keep is exactly what the target would have produced on its own, because it *is* the target's argmax at that position given the same prefix.

in fig. 02 the draft guesses "the cache is slow now", the target agrees on "the cache is" and wants "full" where the draft said "slow". four tokens come out of one read of the weights.

that's the whole argument for losslessness. it rests on one assumption that nobody states out loud. the target's logits for a position inside a batch have to equal its logits for that position when it runs alone.

## that assumption is false

in my first measured run, stock llama.cpp speculative decoding matched plain decoding on 8 of 24 runs. the mismatches were deterministic. run them twice and they diverge at the same byte. one prompt flipped `from typing import Dict, Optional, Any` into `Dict, Any, Optional`. another rewrote a sentence starting at byte 478.

this isn't sampling noise. everything is greedy. the target's logits really are different when it sees 5 tokens at once instead of 1.

## float addition depends on order

real numbers satisfy (a + b) + c = a + (b + c). floats don't. a 32 bit float has 24 bits of precision, so near 100,000,000 the gap between neighbouring representable numbers is 8. add 1 to 100,000,000 and the result rounds straight back to 100,000,000. so (100000000 + 1) - 100000000 is 0, and (100000000 - 100000000) + 1 is 1. same three numbers. different answer.

![fig. 03: float addition depends on order, and the kernel's warp split decides the order.](/assets/img/hiraishin/fig-03.png)

a dot product over 4096 or 12288 numbers is a long sum, and a gpu never adds it left to right. it splits the work across threads and warps, each piece builds a partial sum, then the partials get combined. the split decides the order, and the order decides the rounding.

here's the catch. kernels in llama.cpp are tuned per batch size. the mat-vec kernel that handles a single token uses 4 warps per row on my gpu. the same kernel with 5 to 8 tokens uses 2 warps per row. fig. 03 shows what that does to one row. same chunks, grouped differently, rounded differently. the logits drift, and when the top two candidates are close, the argmax flips.

how close is close? in my stock runs the logits moved by up to 3.7, and the flips happened where plain decoding's top two logits were only 0.008 to 0.28 apart. a 0.008 margin on a 20ish logit is a coin flip for rounding noise.

## finding the bugs: replay the answer

"sometimes the output differs" is a useless bug report. i needed a number per batch size. the trick that worked is teacher forcing. run plain decoding, keep every token and every top logit. then feed that exact token sequence back through the target in batches of B tokens and compare each position's logits with what plain decoding produced. if batched math matches single token math, every difference is 0.000000. anything else is a bug, and you know the batch size and the position.

the fork i used ships a `GGML_CUDA_BATCH_INVARIANT` switch that forces some kernels onto batch invariant paths. with it on, batches of 2 and 3 tokens came back bit exact. batches of 5 and 9 did not. so the switch covered part of the problem. the rest was four separate bugs.

## bug 1: the warp split

the first one is the mat-vec split from fig. 03. the fix is to make every column of a multi token mat-vec use the warp count the single token kernel uses, so each column sums in exactly the same order as a token decoded alone. one rule makes this safe. the single token path stays untouched. the reference is the unmodified model, and the patched build reproduces stock plain decoding token for token on all 45 eval prompts.

there was a second half. past 5 to 7 tokens, k-quant weights switch to a completely different matmul kernel (mmq) with tiled sums. that kernel is fast and has no relation to the single token order. so in batch invariant mode the patch keeps everything up to 16 tokens on the mat-vec path, splitting more than 8 columns into chunks.

## bug 2: a different attention kernel

attention had the same disease. for one query the fork uses a vector kernel, for several queries a different one. the fork's switch already forces the vector kernel for up to 8 queries. i raised that to 16 so drafts of 8 still verify on the same code path.

## bug 3: the 256 boundary

this one took a while to see. llama.cpp doesn't attend over exactly the cells that exist. it rounds the kv length up to a multiple of 256 and masks the extra cells.

![fig. 04: a verify batch that crosses 256 attends over twice as many cells as the same token decoded alone.](/assets/img/hiraishin/fig-04.png)

token 255 decoded alone attends over 256 cells. put the same token in a verify batch at positions 254 to 257 and every token in that batch attends over 512 cells, because the batch reaches past 256. the extra cells are masked to minus infinity, so in exact arithmetic they add nothing. in fp32 the attention kernel splits its work by the kv length, so a longer range means a different split and different rounding.

the fix lives in the speculative loop, not the gpu code. a verify batch never crosses a multiple of 256. if a draft would cross it, cut the draft short and start the next cycle at 256. it costs one shorter draft every 256 tokens.

## bug 4: the one that waited for position 384

after the first three fixes, three of my four prompts were bit exact at every batch size. the fourth, a rewrite prompt with a long input, still showed a logit difference of 0.338. no argmax flip, so the output happened to survive, but a lossless claim can't rest on luck. the difference was identical at every batch size and appeared at one place, kv position 390. the other prompts never got past position 384.

![fig. 05: the batched attention kernel split the kv cache differently, and it only mattered past position 384.](/assets/img/hiraishin/fig-05.png)

the vector attention kernel splits the kv cache into parallel blocks and merges their partial results at the end. how many blocks it uses depends on gpu occupancy, how many copies of the kernel fit on one streaming multiprocessor at once. the 1 query kernel and the 2 query kernel are different compiled kernels with different register counts, so their occupancy differs and so does the block count.

with 512 cells in tiles of 128, a query at position 300 has nothing real in the last tile. it's all masked. fold that tile into block 0 or give it its own block, the sum is the same. a query at 390 has real cells in that tile. folding it into block 0's running sum changes the order of additions. that's why it waited for 384.

the fix is a few lines. when a batched launch picks its block count, it asks for the occupancy of the 1 query kernel instead of its own. after that, every prompt was bit exact at batch sizes 2 through 16.

## exact is expensive

correctness was done. speed was a problem. stock llama.cpp had been fast at 6 to 9 tokens because it switched to the tiled matmul. my exact path stayed on the mat-vec, and the mat-vec with many columns is slow. verifying 9 tokens cost 3.33x a single token pass.

![fig. 08: what one target pass costs as the batch grows. stock is cheap past 5 tokens because its sums are not exact.](/assets/img/hiraishin/fig-08.png)

my first guess was that the kernel re-decodes the 4 bit weights once per column, so i wrote one that unpacks each weight block once and reuses it across all columns. it calls the exact same per column dot product functions as the stock kernel, so the arithmetic stays bit identical. it was slower. 2.70x at 8 tokens against 2.01x for the generic path.

reading the compiled sass explained it. the compiler had already shared the weight loads across columns. the real difference was registers. the 1 column kernel used 48 registers per thread, the 8 column kernel used 108 to 168, so only about 12 warps fit per sm instead of about 40. a kernel that spends its life waiting on memory needs many warps in flight to hide that wait.

two changes fixed it. dropping runtime row checks out of the inner loop let the compiler schedule loads properly, and asking the compiler for 4 blocks per sm capped registers at 128 with no spills. 8 tokens went from 2.66x to 1.74x and 9 tokens from 3.33x to 1.96x, still bit exact. asking for 5 blocks per sm made it worse, 96 registers starved the scheduler the other way. stock is still cheaper past 5 tokens. it buys that with inexact sums.

## two taxes nobody sees

with the kernel fixed, the end to end numbers barely moved. the verify time per cycle sat at 21.1 ms before and after. something outside the kernels was eating the gain.

the first tax was on the draft side. my loop fed the draft model 1 token most of the time and 2 tokens after a fully accepted cycle. a probe showed 2 token batches back to back cost 3.6 ms each, but alternating 1 and 2 cost 8.5 and 6.8 ms. every shape change rebuilt the compute graph. so now every draft call has exactly 2 tokens, re-feeding the previous token when there's only one new one. same shape every time, +13% at draft length 2.

the second tax was cuda graphs. llama.cpp records each forward pass as a cuda graph and replays it, which skips most launch overhead. the cache is keyed by the memory address of the graph's first node. llama.cpp rebuilds the graph for every batch size in the same buffer, so every batch size gets the same key. with adaptive drafting the verify size changes almost every cycle, so the one cached graph was thrown away and re-recorded on nearly every call.

![fig. 06: every batch size shared one cuda graph cache slot, so a changing verify size re-recorded the graph.](/assets/img/hiraishin/fig-06.png)

the fix puts the node count and the token counts into the key, so each batch size keeps its own recorded graph. the cache already supported many graphs. it just never got more than one key. the varying size penalty dropped to noise, and the lossless setup went from 98.8 to 102.9 tok/s on the small prompt set.

## the drafter sets the ceiling

a fixed draft length is a bad bet. stock speculative decoding with 8 guesses per cycle fell to 35 tok/s on creative writing, slower than not speculating at all, because the draft is wrong early and the target pays to verify 9 positions every time.

the loop here stops drafting when the draft model is unsure. after each guess it looks at the gap between its top two logits, and if the gap is under 3 it stops and sends what it has. a confident draft runs long and an unsure one stops after a token or two.

![fig. 07: one average cycle of the 45 prompt eval against plain decoding, drawn to scale.](/assets/img/hiraishin/fig-07.png)

fig. 07 is one average cycle over the whole eval, drawn to scale. 8.5 ms of drafting, 19.0 ms of verifying, 0.4 ms of bookkeeping, and 2.52 tokens out. that's 11.1 ms per token against 16.1 ms for plain decoding.

the 2.52 is the ceiling now. the kernels can still get faster, but the bigger lever is a drafter that guesses better.

## all 45 prompts

the first test set was 4 prompts. it found the bugs. it also flattered the result, because one of the 4 asked the model to copy its input. so the final numbers come from 45 prompts in 8 categories, up to 1024 tokens each, with inputs up to 2,639 tokens, all in one session on ac power.

![fig. 09: 45 prompts in 8 categories, every speculative output checked token for token against plain decoding.](/assets/img/hiraishin/fig-09.png)

| setup | mean tok/s | median | slowest 10% | outputs identical to plain |
|---|---:|---:|---:|---|
| plain decode | 61.4 | 61.7 | 60.7 | n/a |
| stock speculative, 8 guesses | 76.6 | 71.4 | 35.5 | 8 of 45 |
| this, adaptive draft | **92.3** | **91.1** | 75.3 | **45 of 45** |

math gets 108 tok/s, structured output 105, code generation 98, code edits 94, summaries 91, explanations 84, creative writing 76 and long documents 77. stock beats it on math and structured output, 121 and 107, while getting 7 of those 11 outputs wrong.

## things that didn't work

**a 2 bit drafter.** a 0.6b model in 2 bits is about 40% of the size of the 8 bit one. it generated garbage on its own, and its perplexity log read 34,558,588. acceptance was 0.0%.

**n-gram drafting.** before calling the draft model, look for the last 3 tokens earlier in the text and propose whatever followed them. on the copy-heavy prompt it took speed from 119 to 153 tok/s. on the 45 prompt set it was slightly worse, 89.8 against 92.3. off by default.

**padding every verify to one size.** a fixed shape avoids graph re-recording, but capping drafts at 3 tokens lost more than it saved. the per shape cache key made it pointless anyway.

**an eagle-3 head.** eagle-3 drafts with a single trained layer that reads the target's own hidden states, and the fork supports it. a public head for qwen3-8b reached 30 to 37% acceptance on code, math and explanations through the fork's own loop, 61 to 69 tok/s, about plain speed. that loop also lacks the 256 boundary guard, and one output diverged. this needs proper integration before it says anything.

**running on battery.** on battery the driver capped the gpu at 55 w and the memory clock dropped from 11001 to 9001 mhz. plain decoding lost 15%. every comparison in this post was measured in one session, plugged in.

## where the 100 is

on the small prompt set this setup crosses 100 tok/s, 102.7, and 110 with n-gram drafting. on the 45 prompt set it's 92. per cycle the math is tokens per pass divided by cycle time, so there are two ways up. cut the 19 ms verify toward the 16 ms floor of reading the weights once, or raise the 2.52 tokens per pass. a drafter that reads the target's hidden states is the obvious way to raise it, and the eagle-3 numbers above say the integration has to be done properly before it pays.

everything here runs on a stock llama.cpp fork plus five patches and a benchmark harness. each check above, bit exact logits, 45 of 45 identical outputs, the probe numbers, comes from a script that reads a saved log. the 256 boundary and the occupancy split live in every batched decode in that codebase, speculative or not, so the next people to hit them will probably be debugging something else.
