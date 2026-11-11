---
title: a bias that does nothing broke pythia in bf16
date: 2026-11-11
description: activation patching on pythia-160m in bf16 said mlp layer 4 brings back 43% of the answer. fp32 said 3%. the cause was a key bias that cancels inside softmax and grew to 279 during training anyway.
tags: Interpretability, Numerics, Attention, Pythia
cover: /assets/img/kerneltrace-cover.png
---
i ran the same activation patching sweep on pythia-160m twice, once in fp32 and once in bf16. same weights, same 48 prompts. fp32 said mlp layer 4 brings back 3% of the answer. bf16 said 43%.

on 25 of the 48 prompts bf16 saw no effect at all, because the clean run and the corrupted run came out with the same logit diff, so there was nothing for a patch to bring back.

[github.com/Cintu07/kerneltrace](https://github.com/Cintu07/kerneltrace) has the code and every number below. it's a tool i've been building that makes you write an interpretability claim down before you measure it, and then tries to break it. rerunning the experiment in another number format is one of the ways it attacks a claim.

![fig. 1: the same patching sweep in fp32 and bf16. bf16 credits layer 4 with almost half the answer.](/assets/img/kerneltrace/fig-01.png)

## the setup

the task is indirect object identification. in "When John and Emily arrived at the office, John handed the bone to", the model should say Emily. the corrupted prompt swaps the second John for Emily, which pushes the model toward John. the number i track is the logit diff, the logit for Emily minus the logit for John at the last position.

patching takes one mlp layer's output from the clean run and puts it into the corrupted run. if the logit diff comes most of the way back, that layer is carrying the answer. in fp32, layer 0 brings back 0.99 of it and no other layer gets past 0.09.

## first suspect, the output

pythia-160m's logits for these names sit near 836, and bf16 keeps only 8 significant bits, so between 512 and 1024 it can hold every fourth number and nothing in between. a logit diff of 5 comes out as 4, 8 or 0. that looked like the zeros.

gpt-2 small has a milder version of the same thing. its logits sit around 80, where bf16 steps by 0.5. one prompt gave −1.5 run alone and −1.0 as one row in a batch of 15 copies of itself. fp32 gave −1.2814 both ways. doing only the last matmul, the unembedding, in fp32 got that to −1.2537 and −1.2168, and took gpt-2's median patching error from 0.027 to 0.006. i wrote about the same kind of batch-shape rounding in [speculative decoding](/posts/batch-invariance/).

on pythia it made things worse. the median patching error went from 0.10 to 0.46, which meant the output grid was only a small part of whatever was going on.

## the error is in attention

i kept one kind of block in fp32 at a time and left the rest in bf16, with the unembedding in fp32 in every run.

![fig. 2: which part of pythia-160m has to stay in fp32. only attention matters.](/assets/img/kerneltrace/fig-02.png)

mlps in fp32 did almost nothing. layernorms, nothing. attention in fp32 took the median error in the logit diff from 2.73 to 0.086.

the attention scores were huge. from layer 3 on, the biggest score a query gave any key was in the thousands, and in layer 11 it was 115,448. but the scores barely differed between keys. in that layer, the worst head's scores for one query spread over 86 across all the keys it could see. bf16 steps by 512 at that size.

## one head

![fig. 3: one head in layer 10, before and after its scores are rounded to bf16.](/assets/img/kerneltrace/fig-03.png)

head 9 in layer 10, reading the last word. every score is between 35,622 and 35,642, and in fp32 the head puts 86% of its attention on "When". round the scores to bf16 and all fourteen become 35,584. softmax over fourteen equal numbers gives 7% to each, so the head stops looking anywhere in particular.

## where the offset comes from

![fig. 4: the key bias adds the same number to every score a query makes, and softmax removes it.](/assets/img/kerneltrace/fig-04.png)

it's the key bias. a head builds the key for token j as W·x + b, so the score of that key is q·(W·x) + q·b. the second term has no j in it. every key gets the same q·b, and softmax of s + c is the same as softmax of s, so it does nothing.

pythia applies rotary embeddings to the first quarter of each head's dimensions, and rotary turns the bias by position there, so that quarter does reach the attention pattern. in the other three quarters the bias is the same for every key. in pythia-160m that part of the bias has a norm of up to 279. the part rotary touches stays under 20. the query bias stays under 9.

## it grew anyway

![fig. 5: the invariant part of the key bias over pythia-160m's training, and in the final weights of every pythia size.](/assets/img/kerneltrace/fig-05.png)

a term that softmax cancels gets no gradient from the loss, at least in exact math. it was 0 at step 0, 1.0 at step 1,000, 28 at 8,000, 120 at 32,000 and 279 at the end, step 143,000. i don't know what moved it. my guess is adam, which divides each update by the recent size of the gradient, so a gradient made of nothing but rounding noise still gets full-size steps. i haven't tested that.

pythia's training checkpoints are published as separate branches. a safetensors file starts with a json header that says where each tensor sits, so i read only the 12 bias tensors out of each checkpoint with http range requests, a few kilobytes each. the same reader went through the final weights of every pythia size, up to 12b. 70m, 160m, 410m and 1.4b are over 100. 1b is at 18, and its bf16 numbers were fine all along.

## it isn't only patching

perplexity on the start of the wikitext-2 test set, 64 windows of 512 tokens, as a change from fp32.

| model | bf16 | fp16 | bf16, bias dropped | fp16, bias dropped | bf16, fp32 attention and head |
|---|---|---|---|---|---|
| gpt-2 small | +1.0% | +0.0% | +0.9% | +0.0% | −0.2% |
| pythia-70m | +870% | nan | +396% | +3.1% | +0.6% |
| pythia-160m | +171% | nan | +61% | +0.8% | +0.3% |
| pythia-410m | +19.6% | nan | +0.1% | +0.0% | +0.0% |
| pythia-1b | +0.0% | +0.0% | +0.0% | +0.0% | +0.0% |
| pythia-1.4b | +5.7% | nan | +2.1% | nan | +0.4% |

pythia-70m goes from 68 to 659 in bf16. in fp16, four of the five pythia sizes i ran give nan on every window, because numbers inside their attention pass 65,504, the largest one fp16 has.

## deleting it

so i deleted it.

```python
from kerneltrace.models.precision import drop_invariant_key_bias
drop_invariant_key_bias(adapter)  # zeroes the key bias outside the rotary dims
```

in fp32 the logits move by at most 0.007 after this, which is about how much fp32 drifts when the batch size changes. pythia-410m then runs in plain bf16 within 0.1% of fp32 perplexity, fp16 stops giving nan on it, and the patching sweep lands within a median of 0.007 of fp32 with the same top three layers.

it doesn't fix everything. 70m and 160m still need the unembedding in fp32, because their logits still sit near 836. 1.4b still overflows fp16, because the attention code multiplies q by k before it scales, and that raw product reaches 129,160 even with the bias gone. keeping attention and the unembedding in fp32 works on all six models, within 0.6% of fp32 perplexity. it costs more memory than deleting a bias does.

## what i got wrong

i committed predictions to the repo before each batch of runs. 15 of them. 8 held. i expected pythia's bf16 batch jumps to be bigger than gpt-2's, and the median was smaller, because a grid of 4 swallows small drift and only jumps on a few prompts, by 4 or 8. i expected the fp32 unembedding to fix pythia, and the problem was in attention. i expected 160m's 25 lost prompts to stay lost after deleting the bias, because of the output grid, and all 25 came back. the other misses are in `experiments/` next to the results.

all of this is one task and one model family, run up to 1.4b and read up to 12b. i haven't looked at other models that have a key bias.
