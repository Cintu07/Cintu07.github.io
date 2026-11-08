---
title: a diff engine in assembly, and a viewer that opens a million lines
date: 2026-11-08
description: on writing a line diff in nasm, porting it to webassembly by hand, and drawing the result on the gpu so a million-line diff opens in a fifth of a second.
tags: assembly, simd, webassembly, webgl, performance
cover: /assets/img/seams-cover.png
---
git diffs a million-line file before you've let go of enter. put the same diff in a web viewer and you wait. the best javascript library i measured took six seconds to show the first screen and forty-one to finish highlighting. so the slow part in the browser was never really the diff. it was everything around it.

that's how seams started. it's a line diff engine written in x86-64 assembly, the same engine written again by hand in webassembly so it runs in a browser, and a viewer that draws on the gpu. on my laptop a million-line diff shows its first screen in about 0.19 seconds and scrolls at the refresh rate of the display. this post is how it gets there, and most of the answer is "it skips work".

## what a diff actually is

a line diff answers one question: what's the smallest set of lines i can delete from the old file and insert into the new one to turn one into the other? the classic answer is myers' algorithm from 1986. picture a grid with the old file's lines down one side and the new file's lines across the other. moving right is an insert, moving down is a delete, and wherever two lines match you get a free diagonal step. the shortest diff is the path from the top-left corner to the bottom-right with the fewest non-diagonal steps.

seams runs that in seven stages, and each stage is its own file:

1. scan: find where every line starts and how long it is.
2. trim: skip the identical lines at the start and end.
3. hash: give every remaining line a 64-bit hash.
4. intern: turn each distinct line into a small integer id.
5. myers: find the shortest edit path over those ids.
6. emit: turn "this line changed" into change records.
7. apply: rebuild the new file from the old one and the records, to prove the records are right.

after stage four, the algorithm never looks at text again. `return x;` is just id 412, and comparing two lines is comparing two integers.

## the first rule: name everything

assembly has a reputation for being unreadable. what makes it unreadable is mostly registers. `mov [r8 + rcx*4], r11d` tells you nothing. so the first rule in this codebase was that every register gets a name before it's used:

```nasm
%define bytes rdi
%define length rsi
%define cursor rcx
%define starts r8
%define line_start r11
%define line_start32 r11d
```

after that, the line above reads `mov [starts + cursor*4], line_start32`, and you can review it. the names cost nothing at runtime because nasm swaps them back before it assembles anything. the second rule was that every struct offset lives in one file, `layout.inc`. the bug i was most scared of was reading field seven when i meant field six, and with one source of truth that becomes an assembler error instead of a wrong answer at 2am.

## finding a million newlines

the scanner is the first thing that touches the file, so it runs once per byte. a plain loop compares one byte with `\n`, branches, and moves on. the avx2 version reads 32 bytes at once:

```nasm
vmovdqu chunk, [bytes + cursor]
vpcmpeqb chunk, chunk, newline     ; 0xff wherever a byte is '\n'
vpmovmskb mask, chunk              ; squash that into one bit per byte
```

`newline` is a register holding 32 copies of the byte 10. after those three instructions, "where are the newlines in these 32 bytes" turns into "which bits are set in this 32-bit integer". two more instructions finish the job. `tzcnt` finds the lowest set bit, which is the next newline, and `blsr` clears it. the loop runs once per newline instead of once per byte, so on source code it branches about once every forty bytes.

there's also a scalar version in the same file, and i wrote it first on purpose. it's the spec. the test harness runs both on twenty thousand random buffers, and the avx2 one has to produce exactly the same table every time.

## most of the speed comes from not diffing

real edits are small. you change twelve lines in the middle of a five-thousand-line file, and everything above and below is identical. so before hashing anything, seams finds the longest common prefix and suffix of the raw bytes, eight at a time with one 64-bit xor, then binary searches the line table to round them to whole lines. those lines can never be part of a minimal diff, so the expensive stages never see them.

i benchmarked this on 3,000 real before-and-after pairs of `.c` and `.h` files pulled from linux kernel commits. seams takes 166 ms for all of them, and imara-diff, a fast rust library, takes 319 ms with its default myers. most of that gap is the trim. the fastest diff is the one you skip.

the honest other side: on files with ten thousand edits scattered all through them, seams in exact mode is 2.2 to 2.7 times slower than imara. it insists on the minimal answer, and imara's default trades a little minimality for speed.

## when myers takes forever

exact myers has a nasty worst case. take two files that contain the same lines in a different order, and the search can wander the grid for a very long time. on 40,000 shuffled lines the exact search took 5.4 seconds.

the fix is a budget. the linear-space version of myers searches from both corners at once, forward from the top-left and backward from the bottom-right, until the two searches meet somewhere in the middle. that meeting point is the "middle snake", and the problem splits there into two smaller ones. in fast mode, each of those searches gets roughly the square root of the problem size in rounds. if it runs out, it stops looking for the perfect meeting point and splits at the furthest point the forward search reached. the same 40,000 lines now take 0.9 seconds, and the diff is 0.33% longer. fast mode is the default, and `--minimal` gives you the exact one back.

## the browser can't run x86

so i wrote the whole pipeline again in webassembly text, the human-readable form of wasm, by hand. simd in wasm is 16 bytes wide instead of 32, so the scanner and the trim work in half-size steps. the compiled module is about 5 kb.

the important part is the test. for every random pair the native fuzzer generates, the wasm version has to produce exactly the same change records as the assembly. that test caught most of my porting mistakes within minutes.

it also caught the strangest bug of the project. one day the wasm build got 175 times slower: 42 ms on 100,000 lines became 7.4 seconds, and the output was still correct. there's a test-only build of the engine with a deliberately terrible hash, where every line collides with half the file, and the build script strips that hash out of the real build with a regex. a file had been saved with windows line endings. the regex expected `\n` and saw `\r\n`, so it matched nothing, and the terrible hash went into the real build. every lookup collided, every collision got checked byte by byte, and so the answer stayed right and got very slow. normalising line endings in the build script fixed it, and the build now runs at 43 ms for exact mode and 19 ms for fast.

## drawing a million lines

the diff was never the bottleneck in the browser. a normal viewer builds html: a div per line and a span per highlighted token. at a million lines that's millions of dom nodes, and layout alone takes seconds.

seams draws on a canvas with webgl2. every character on screen is one small rectangle, and its letter comes from a glyph atlas, a texture with each character drawn once. each frame, the viewer works out which rows are visible, fills one buffer with "this glyph, at this spot, in this colour", and paints the lot with a single instanced draw call. that costs about 0.2 ms of cpu per frame no matter how long the file is. on my 145 hz display the slowest 1% of frames still come in under 8 ms.

the price is that the browser gives you nothing for free on a canvas. text selection, copy, find, and a hidden list of the visible lines for screen readers all had to be built by hand.

against a popular javascript diff library at its best settings, on the same million-line pair: first screen in 0.19 seconds against 6, fully highlighted in half a second against 41, and smooth scrolling against about a third of the frame rate. most of their first-screen time is their javascript diff, not their renderer, and their syntax highlighting is more accurate than my small lexers. the scrolling gap holds either way, because it's dom nodes against one draw call.

## a friend's idea: don't diff in the browser at all

i showed this to a friend who does a lot of web performance work, and his first question was why the browser was computing the diff at all. if a diff is going to be viewed, like on a pull request page, compute it once on the server, ship the result, and let the browser only scroll.

he was right, so seams has packs now. a `.seamspack` file holds both files, their line tables, the edit script and the highlighter's state at each line, all laid out as typed arrays the viewer can use directly. with a pack, a million-line diff shows its first frame in 34 ms instead of about 500, measured on my laptop on battery.

## patches and merges

two smaller things fell out of having a fast, exact engine.

a seams patch carries its inserted lines inside it, so you only need the old file to apply it. a hundred-edit change to a 32 mb file is a 7.5 kb patch. it also stores the length and hash of the file it was made from, so applying it to the wrong file fails loudly instead of producing garbage.

and there's a three-way merge. it takes two edits of the same base file, keeps whichever side changed a region, takes identical changes once, and writes git-style conflict markers when both sides touched the same lines differently. it's checked byte for byte against a plain c version of the same algorithm on a hundred thousand random cases.

## what's still missing

emoji draw in one colour, and combining accents don't draw at all. a pull-request-sized view with five thousand files isn't built yet. the fast mode hasn't been benchmarked against imara-diff, only exact mode has. and there's no mac or windows binary yet.

the code is on github at [cintu07/seams](https://github.com/Cintu07/seams), and the site at [cintu07.github.io/seams](https://cintu07.github.io/seams) runs the real viewer on seams' own source and on the million-line demo. you can also drop two of your own files in, and nothing leaves your machine. if you have a diff that breaks everything else, i'd like to see it.
