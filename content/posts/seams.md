---
title: seams, a diff engine i wrote in assembly
date: 2026-11-08
description: a line diff written by hand in x86-64 assembly, ported by hand to webassembly, drawn on the gpu. a million-line diff opens in a fifth of a second.
tags: assembly, simd, webassembly, webgl, performance
cover: /assets/img/seams-cover.png
---
git diffs a million-line file before your finger leaves the enter key. the browser is a different story. paste the same two files into a web diff viewer and go make tea. the best javascript library i measured needed six seconds for the first screen and forty-one to finish highlighting.

so i wrote seams. it's a line diff engine in x86-64 assembly, written a second time by hand in webassembly so it runs in a browser, plus a viewer that draws every character on the gpu. a million-line diff shows up in about 0.19 seconds. then it scrolls at whatever your monitor refreshes at. the trick is refusing to do work.

## the whole pipeline fits on a napkin

a diff answers one question. which lines do i delete from the old file and insert into the new one to get from one to the other, and what's the fewest i can get away with? the standard answer is myers' algorithm from 1986. draw the old file down the side of a grid and the new file across the top. a step right inserts a line, a step down deletes one, and every pair of matching lines gives you a free diagonal. the best diff is the corner-to-corner path with the fewest non-diagonal steps.

seams gets there in seven stages, one file each.

1. scan finds where every line starts and how long it is.
2. trim skips the identical lines at the top and bottom.
3. hash gives every remaining line a 64-bit fingerprint.
4. intern turns each distinct line into a small integer.
5. myers finds the shortest path over those integers.
6. emit turns "this line changed" into change records.
7. apply rebuilds the new file from the old one plus the records, which is how the tests know the records are right.

after stage four the text is gone. `return x;` becomes 412, and comparing two lines costs one integer compare.

## every register gets a name

assembly has a reputation for being write-only. blame the registers. `mov [r8 + rcx*4], r11d` tells you nothing about what's going on.

so rule one in this codebase is that no register gets used before it gets a name.

```nasm
%define bytes rdi
%define length rsi
%define cursor rcx
%define starts r8
%define line_start r11
%define line_start32 r11d
```

now that same line reads `mov [starts + cursor*4], line_start32`, and a reviewer can follow it. that's all it takes. nasm swaps them back before assembling. zero runtime cost. rule two puts every struct offset in one file, `layout.inc`. the bug that scares me most in asm is reading field seven when i meant field six. with one source of truth that bug dies at assemble time, long before it can hand me a wrong answer at 2am on a friday night.

## thirty-two bytes per step

the scanner touches every byte. hottest loop in the program. the plain version compares one byte against `\n`, branches, moves on. the avx2 version eats 32 bytes per step.

```nasm
vmovdqu chunk, [bytes + cursor]
vpcmpeqb chunk, chunk, newline     ; 0xff wherever a byte is '\n'
vpmovmskb mask, chunk              ; one bit per byte
```

`newline` holds 32 copies of the byte 10. three instructions later, "where are the newlines in these 32 bytes" has become "which bits are set in this integer". `tzcnt` returns the lowest set bit, which is the next newline. `blsr` clears it. repeat until the mask hits zero. the loop now runs once per newline. on source code that's one branch every forty bytes or so.

i wrote the scalar version first. it's the spec. the test harness feeds both versions twenty thousand random buffers, and they have to agree on every entry, every single time, or the build fails.

## the fastest diff is the one you skip

real edits are tiny. you touch twelve lines in the middle of a five-thousand-line file and the rest is byte-for-byte identical. so before hashing anything, seams walks in from both ends eight bytes at a time with one 64-bit xor, then binary searches the line table to round to whole lines. the expensive stages never see those lines.

i ran this over 3,000 real before-and-after pairs of `.c` and `.h` files from linux kernel commits. seams finished all of them in 166 ms, and imara-diff, a fast rust library, took 319 ms with its default myers. the trim is most of that gap.

it loses too. on files with ten thousand edits sprayed through them, exact mode runs 2.2 to 2.7 times slower than imara. seams insists on the minimal diff there, and imara's default happily trades a little minimality for speed.

## giving myers a budget

exact myers has an ugly worst case. hand it two files with the same lines in a different order and it wanders the grid for ages. 40,000 shuffled lines took 5.4 seconds. way too long.

the linear-space version of myers searches from both corners at once and splits the problem wherever the two searches meet. that meeting point is called the middle snake. in fast mode each search gets a budget of roughly the square root of the problem size. when the budget runs out it stops hunting for the perfect split and just cuts at the furthest point the forward search managed to reach. same 40,000 lines, 0.9 seconds, and the diff came out 0.33% longer. it's the default now. `--minimal` brings back the exact one.

## the browser can't run x86, so i wrote it again

the whole pipeline exists a second time in webassembly text, written by hand. wasm simd is 16 bytes wide, so the scanner and the trim take half-size steps. the compiled module is about 5 kb.

the test that keeps them honest is brutal. for every random pair the native fuzzer generates, the wasm build has to produce the exact same change records as the assembly. it caught most of my porting bugs within minutes.

it also caught the weirdest bug of the whole project. one afternoon the wasm build got 175 times slower. 42 ms on 100,000 lines turned into 7.4 seconds. the answers? still correct. there's a test-only build with a deliberately awful hash, where every line collides with half the file, and the build script cuts that hash out of the real build with a regex. one file had been saved with windows line endings. the regex wanted `\n`, found `\r\n`, matched nothing, and the awful hash shipped in the real build. every lookup collided and every collision got checked byte by byte, so the answers stayed right while the speed died. one line that normalises line endings fixed it. exact mode is back to 43 ms, and fast mode does it in 19.

## one draw call for a million lines

in the browser, rendering is the slow part. a normal viewer builds html, a div per line and a span per coloured token. a million lines means millions of dom nodes, and layout alone eats seconds.

seams draws on a canvas with webgl2. each character is a tiny rectangle that samples its letter from a glyph atlas, a texture with every character drawn once. per frame, the viewer works out which rows are visible, fills one buffer with "this glyph, here, this colour", and paints the lot in a single instanced draw call. that's about 0.2 ms of cpu per frame whether the file has a hundred lines or a million. on my 145 hz display the slowest 1% of frames still land under 8 ms.

the catch? a canvas gives you nothing for free. selection, copy, find, and a hidden list of visible lines for screen readers all had to be built by hand.

side by side with a popular javascript diff library at its best settings, on the same million-line pair, seams shows the first screen in 0.19 seconds against 6, finishes highlighting in half a second against 41, and scrolls at full frame rate where theirs manages about a third. to be fair to them, most of their first-screen time is their javascript diff, and their syntax highlighting is more accurate than my little lexers. the scrolling gap holds either way. thousands of dom nodes lose to one draw call.

## a friend asked why the browser diffs at all

i showed this to a friend who lives and breathes web performance. his first question was why the browser computes the diff in the first place. if a diff is going to be viewed, say on a pull request, compute it once on a server, ship the result, and let the browser just scroll.

he was right. a `.seamspack` file now carries both files, their line tables, the edit script and the highlighter's state at every line, laid out as typed arrays the viewer uses as is. with a pack, a million-line diff paints its first frame in 34 ms instead of around 500, measured on my laptop on battery.

## patches that bring their own lines

two side quests fell out of this.

a seams patch carries its inserted lines, so applying it only needs the old file. a hundred-edit change to a 32 mb file packs into 7.5 kb. it also records the length and hash of the file it came from, so pointing it at the wrong file fails loudly, before a single byte gets written.

and there's a three-way merge. give it two edits of the same base and it keeps whichever side touched a region, takes identical changes once, and writes git-style conflict markers when both sides changed the same lines differently. a plain c version of the same algorithm checks it byte for byte on a hundred thousand random cases.

## using it

in a web page, import it straight from the site. no install, no package manager.

```js
import { createDiffViewer } from 'https://cintu07.github.io/seams/lib/index.mjs';

const viewer = createDiffViewer(el);
await viewer.setFiles(before, after, { name: 'main.ts' });
```

on linux x86-64, grab the static binary from the [releases](https://github.com/Cintu07/seams/releases) and run `seams old new`. `seams patch`, `seams apply` and `seams merge` do what they say. or drop two files on [the site](https://cintu07.github.io/seams) and nothing leaves your machine.

## still on the list

emoji draw in one colour, and combining accents don't draw yet. a pull-request view with five thousand files doesn't exist. fast mode hasn't been raced against imara-diff, only exact mode has. there's no mac or windows binary yet.

the code lives at [cintu07/seams](https://github.com/Cintu07/seams). if you have a diff that breaks everything else, send it to me, because i'd honestly love to watch it break seams too.
