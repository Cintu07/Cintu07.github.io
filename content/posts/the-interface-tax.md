---
title: the interface tax
date: 2026-10-04
description: inference larping maybe?
tags: gpu, performance, ml compilers, tinygrad, vulkan
---
october 2026 / pawan

every perf conversation i see online starts at the kernel. someone made a matmul faster, someone rewrote softmax in triton, someone posted a speedup graph with a nice green bar. and i get it, kernels are the fun part. but the more time i spend inside this stuff, the more i believe the kernel is rarely what decides how fast your program is. the first thing that decides it is the interface you describe the work through, and almost nobody questions that part.

i've started calling it the interface tax. every layer you build on charges you something before your code even runs, and no amount of tuning underneath gets that money back.

so here is a small exercise. take any computation and ask three things. what does the interface let me say? what does the hardware actually want? and what am i paying for the gap? let's do a few.

## three kernels walk into a memory bus

take `y = relu(x * a + b)` on 100 million floats. in eager pytorch that is three ops, so three kernels. each one reads its input from gpu memory and writes its result back. that's 400mb per pass and six passes, so about 2.4gb of traffic for math so simple the gpu barely notices it.

do all three in one kernel and you read x once and write y once: 0.8gb. same math, a third of the traffic, and because these ops are limited by memory rather than compute, roughly a third of the time.

why doesn't eager mode just do that? because when it runs `x * a` it has no idea a `+ b` and a `relu` are coming. it can't fuse what it can't see. torch.compile and jax's jit exist precisely because of this: record the whole computation first, then compile it. same python on top, a completely different interface underneath.

## the n by n matrix that never needed to exist

attention written the textbook way is three ops: `QK^T`, softmax, then multiply by v. the middle step writes the full n by n score matrix out to gpu memory and reads it back in. at long sequence lengths that matrix is enormous.

flashattention computes the same thing in tiles that stay in fast on-chip memory and never writes that matrix out at all. the memory for that intermediate drops from o(n²) to o(n). the math didn't change. what changed is that someone refused to express it as three separate ops, because the three-op interface had a ceiling baked into it.

## oh, your kernel is 2x faster?

cool. what fraction of the runtime was it? say 3%. then the whole program got about 1.5% faster. that's amdahl's law, and it ruins most speedup screenshots.

so where does the rest go? in llm decoding at small batch sizes, a lot of it goes to launching hundreds of tiny kernels per token, each doing a few microseconds of real work, with python and the framework's dispatcher sitting in between. the gpu spends real time idle, waiting to be told what to do next. cuda graphs attack exactly this: record a sequence of launches once, replay all of it with one call. the kernels are identical. only the way work is handed to the gpu changed.

## graphics people already bled for this

real-time graphics went through this years before ml did. you get about 16.7ms per frame at 60fps, every frame, and nobody cares about your average. older apis like opengl and dx11 did a pile of hidden driver work on every draw call, so engines ran out of cpu time long before the gpu was busy. better shaders couldn't fix that. amd's mantle, and then vulkan and dx12, moved that work into the application's hands and made it explicit and cheap. same hardware, a much higher ceiling, because the interface changed.

## my laptop said no

this one i hit on my own laptop. it has an adreno x1-45, and i wanted to try tensor-core style matmuls through vulkan's cooperative matrices. the driver doesn't expose them at all. and it reports 32kb of shared memory per workgroup, where nvidia cards usually report 48kb through vulkan, even though the hardware there physically has more.

whatever the silicon can do, your program only gets what the driver is willing to expose. if you're building something portable, the honest move is to pick a floor the drivers actually support and design around it, instead of chasing every driver up and down.

## a week of my life on one tinygrad bounty

i spent a week on a tinygrad bounty: make kernel arguments work in any order. every backend's launcher packed arguments one fixed way, all the buffers first, then all the scalars. so a kernel that takes `(out, n, in)` simply could not exist. it crashed, or the scalar got quietly moved to the end. nothing about speed fixes that. you change what the launcher is allowed to say, one function that packs arguments in the order the kernel declared them, and suddenly that kernel exists.

most of the hard bugs in that week weren't in the kernels either. they were in the places where one layer quietly assumed something about the layer next to it.

## fine, frameworks aren't evil

interfaces exist for good reasons. eager pytorch is why a whole generation of researchers could iterate fast, and most code never needs to run at the hardware's limit. so this is not "frameworks bad".

it's this: before you post the speedup, profile. if most of the time is round trips to memory, launch overhead, or a limit the driver set, your next kernel won't save you. ask what the interface is forcing on the hardware, and whether you can describe the work some other way.

so the next time someone shows you a 2x on one op, ask them about the other 97 percent.
