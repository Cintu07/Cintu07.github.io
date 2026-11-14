---
title: a diff engine in assembly, and a viewer that opens a million lines
date: 2026-11-08
description: on writing a line diff in nasm, porting it to webassembly by hand, and drawing the result on the gpu so a million-line diff opens in a fifth of a second.
tags: assembly, simd, webassembly, webgl, performance
cover: /assets/img/seams-cover.png
---
i benchmarked the best javascript diff viewer i could find on two files with a million lines each. it took six seconds to show anything and forty-one seconds to finish highlighting. git diff gets through the same pair in a fraction of that, so almost all of the time was going into the browser drawing the result.

seams is what i wrote to fix my side of that. the diff engine is x86-64 assembly. the same engine is written a second time, by hand, in webassembly so it can run in a browser. the viewer draws every character with webgl. on my laptop that million-line pair now opens in 0.19 seconds, the colours are done in half a second, and it scrolls at the full 145 hz of the screen. the javascript library managed about 48 frames a second.


## what the engine does

a line diff answers one question. which lines do you delete from the old file and add to the new one, and what is the smallest set that gets you there? the standard answer is myers' algorithm from 1986. you draw the old file down the side of a grid and the new file along the top. a step right adds a line, a step down deletes one, and wherever two lines are the same you get a free step along the diagonal. the shortest diff is the path from one corner to the other with the fewest steps that aren't diagonal.

seams does it in stages, one file each. it finds where every line starts, skips the lines that match at the top and bottom, hashes what's left, turns each distinct line into a small number, runs myers on the numbers, and writes out the changes. after the fourth stage the text is gone. `return x;` is just 412, and comparing two lines is comparing two integers.

## naming every register

the first rule i set for the assembly was that no register gets used before it has a name. `mov [r8 + rcx*4], r11d` tells you nothing. with `%define starts r8`, `%define cursor rcx` and `%define line_start32 r11d` at the top, the same instruction reads `mov [starts + cursor*4], line_start32`, and somebody else can review it. nasm swaps the names back before it assembles, so it costs nothing.

the second rule was that every struct offset lives in one file, `layout.inc`. the bug i was most worried about was reading field seven when i meant field six. with one source of truth that turns into an assembler error instead of a wrong answer.

## a million newlines

the first stage touches every byte of the file, so it's the hottest loop in the program. the plain version reads one byte, compares it with `\n`, branches, and moves on. the avx2 version reads 32 bytes at once.

```nasm
vmovdqu chunk, [bytes + cursor]
vpcmpeqb chunk, chunk, newline     ; 0xff wherever a byte is '\n'
vpmovmskb mask, chunk              ; one bit per byte
```

`newline` holds 32 copies of the byte 10. after those three instructions the question "where are the newlines in these 32 bytes" has become "which bits are set in this integer". `tzcnt` gives the lowest set bit, which is the next newline, and `blsr` clears it. the loop now goes round once per newline instead of once per byte, which on source code is about once every forty bytes.

i wrote the plain version first and kept it as the spec. the tests run both on twenty thousand random buffers and they have to produce the same table every time.

## most of the speed is in skipping

real edits are small. you change twelve lines in the middle of a five-thousand-line file and the rest is identical. so before it hashes anything, seams compares the two files from both ends, eight bytes at a time with a 64-bit xor, and rounds the matching stretch to whole lines. those lines can't be part of the smallest diff, so the expensive stages never see them.

i tested this on 3,000 real before-and-after pairs of `.c` and `.h` files from linux kernel commits. seams took 166 ms for all of them and imara-diff, a fast rust library, took 319 ms with its default myers. the skipping is most of that difference.

it didn't win everywhere at first. on files with ten thousand edits scattered all through them, exact seams was 2.2 to 2.7 times slower than imara, and the faster mode below still lost by about a third.

## when myers takes forever

myers has a bad case. give it two files that contain the same lines in a different order and it can wander the grid for a long time. forty thousand shuffled lines took 5.4 seconds.

the version seams uses searches from both corners at once and splits the problem where the two searches meet. so i gave each search a budget of about the square root of the problem size. when the budget runs out, it stops looking for the perfect meeting point and splits at the furthest point the forward search got to. the same forty thousand lines take 0.9 seconds that way, and the diff comes out 0.33% longer. that's the default now, and `--minimal` gets you the exact one.

that routine also had a hole in its tests that i only found by accident. while making a video of the code being written, i put a deliberate mistake into it, comparing a position against the wrong side's limit, and the whole test suite still passed. the only cutoff test used two files of the same length, so the search box was square and both limits were the same number. i added lopsided cases, forty thousand lines against fourteen thousand. the mistake crashes those. they also showed the real cost of the shortcut on lopsided files, which is a diff about 9% longer, not 0.33%.

the gap on dense edits closed later, after i read how git's diff and imara handle the same search. once a search has cost more than 256 steps, they check whether either front has just run along more than 20 matching lines, and if a point that far along exists they split there without waiting for the two searches to meet. seams' budget had a floor of 4096 steps, and on a file with an edit every ten lines most of the time went into searches that used all of it. i tried the change in a small c model before touching the assembly. on 100,000 lines with 10,000 edits it did about a seventh of the work and found exactly the same number of edits, so it went into both the assembly and the webassembly. that pair now takes 12.5 ms against imara's 16.1, and a million lines with 10,000 edits takes 89 ms against 115. `--minimal` is still slower than imara on those files, because it won't give up the shortest diff.

## writing it again for the browser

browsers can't run x86, so the whole pipeline exists a second time in webassembly text, written by hand. webassembly's simd is 16 bytes wide instead of 32, so the scanner and the skipping take half-size steps. the compiled module is about 5 kb.

for every random pair the native tests generate, the webassembly version has to produce exactly the same changes as the assembly. that check caught most of my porting mistakes within minutes.

it also caught the strangest bug in the project. one day the browser build got 175 times slower. 42 ms on 100,000 lines became 7.4 seconds, and every answer was still correct. there's a test build of the engine with a deliberately terrible hash, so that every line collides with half the file, and the build script removes that hash from the real build with a regex. one file had been saved with windows line endings. the regex expected `\n`, got `\r\n`, matched nothing, and the terrible hash went into the real build. every collision was still checked byte by byte, which is why the answers stayed right while it got slow. one line that normalises line endings fixed it.

## drawing a million lines

in the browser the drawing is the slow part. a normal viewer builds html, a div for each line and a span for each coloured word. a million lines is millions of elements, and the browser spends seconds just working out where they go.

seams draws on a canvas with webgl2. each character is a small rectangle that takes its letter from a texture with every character drawn into it once. each frame the viewer works out which rows are on screen, fills one buffer with which letter goes where in which colour, and draws all of it with one call. that costs about 0.2 ms of cpu a frame whatever the size of the file, and the slowest 1% of frames still come in under 8 ms.

a canvas comes with none of the browser's usual behaviour, though. selection, copy, find, and a hidden list of the visible lines for screen readers all had to be written by hand. so did whole-character drawing, so that an accent, a hindi conjunct or a family emoji made of three joined emoji comes out as one character instead of pieces.

against that javascript library at its best settings, on the same pair, seams shows the first screen in 0.19 seconds against 6 and finishes highlighting in half a second against 41. to be fair to it, most of its first-screen time is its javascript diff, and its syntax highlighting is better than my small lexers.

the top of a big diff is often the same in both files, and lines that match from the very first one are unchanged in any diff, because the engine sets them aside before it looks for changes. so when two large files open with at least a screen of the same lines, the viewer draws those lines straight away and puts the full diff in when the worker finishes. on the million-line pair, text is up within one frame of the files being in memory, and the whole diff still lands at about 0.19 seconds.

## a friend's idea

i showed this to a friend who does a lot of web performance work, and the first thing he asked was why the browser was computing the diff at all. if a diff is going to be looked at, compute it once on a server and let the browser only scroll.

he was right. a `.seamspack` file holds both files, their line tables, the changes and the highlighter's state at each line, laid out so the viewer can use it straight away. with a pack, the million-line diff shows its first frame in 34 ms instead of about 500, measured on a laptop running on battery.

he made two more points. the first was that most people reading a diff have a slower laptop than mine. chrome's devtools can slow the cpu down six times, so i opened the site's million-line demo that way. the first frame came at 0.46 seconds and wheel scrolling still didn't drop a frame. edge ignores that slowdown inside web workers, which is where seams diffs, so i timed the same wasm again on the main thread, where it does apply, and there the diff took between 0.4 and 0.6 seconds on each run.

the second was that the page shouldn't have to wait for any javascript before you can read the diff. `seams-pack --page` now also writes an html page with the first 60 rows already in it. the text is readable before a script has run, and the viewer takes over on top of it at the same rows once the pack is in. the page is 6 kb, and for the million-line diff its text appears at 156 ms, or at 204 ms with the cpu slowed six times.

## a real pull request

the pull request view puts a file list next to the viewer and diffs every file in the background while you read the first one. i tested it on my fork of tinygrad, with 3,000 commits of real history opened as a single pull request. that's about 1,200 files and half a million changed lines. seams diffed all of them in a quarter of a second, and its totals matched `git diff --minimal` line for line.

## getting it

the quickest way is [the site](https://cintu07.github.io/seams). drop two files on it and they are diffed and drawn in that tab. nothing is uploaded. it also has three screen recordings of seams running and a short guide to each way of using it.

for the command line there are builds on the [releases page](https://github.com/Cintu07/seams/releases). linux gets one static binary, windows gets `seams.exe`, and intel macs get a tarball. `seams old.txt new.txt` prints a unified diff like `diff -u` would. there's also a patch command that writes patches carrying their own lines, so a 32 mb file with a hundred edits travels as 7.5 kb, and applying one to the wrong file is refused. and `seams merge base ours theirs` does a three-way merge with the same conflict markers git uses.

the windows build comes from the same assembly. windows passes function arguments in different registers from linux, so instead of rewriting every routine, the header tells windows compilers to call the engine with the linux convention, and the compiler saves whatever windows needs around each call. ci checks that the windows and mac builds give the linux answers byte for byte.

for a branch in any git repository, clone seams and run

```sh
node path/to/seams/tools/seams-review.mjs main..my-branch
```

and it opens in your browser like a pull request. for github there's a browser extension, `seams-extension.zip` on the releases page, that puts an **open in seams** button next to every pull request title. big pull requests come down as two snapshots of the repository, unpacked while they download, keeping only the files that changed.

the tab it opens stays in step with the pull request. review comments from github show up as small numbered pins on their lines. hover a line number and a + appears, and a comment written there goes up to the pull request under your name. github only takes line comments near a change, so for any other line seams posts a comment on the whole file that starts with `L1980`, and pins it back on line 1980 when it reads it. when someone pushes, the tab notices within ten seconds (two minutes without a token), fetches only the files whose contents changed, and keeps you on the line you were reading. with a token, a check that finds nothing new doesn't count against github's rate limit. so far i've run this part against a fake github server in the tests, not on a live pull request.

## when it's worth using

most diffs are thirty lines and any tool is fine for those. i'd reach for seams when github says the diff is too large to show, when a coding agent has touched a few thousand lines and i still have to read them, for data that happens to be text like sql dumps, logs and csv files, and for comparing two runs of the same job.

in the viewer, `n` and `p` jump between changes, `ctrl f` searches the whole diff and `v` switches to side by side. the highlighting covers about twenty languages, from typescript and rust to shell, sql and the assembly seams is written in. there are seven colour themes, and one of them, `clear`, marks deleted lines orange and inserted lines blue, for people who can't tell red from green. in the pull request view `]` and `[` move between files and the box at the top filters them, so typing `codegen` takes twelve hundred files down to the five you want.

## what's still missing

with `--minimal`, imara-diff's default mode is still faster than seams on files with thousands of scattered edits. there's no arm64 build, so apple silicon macs run the intel one through rosetta. the windows binary isn't signed yet either, so smart app control may block it the first time you run it.

the code is on [github](https://github.com/Cintu07/seams).
