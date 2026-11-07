---
title: your ai has amnesia, and a bigger context window will not fix it
date: 2026-08-10
description: three turns after a user removed their card, i watched the agent tell them it was still on file. same session.
tags: AI Agents, Memory, Machine Learning
cover: /assets/img/your-ai-has-amnesia-cover.jpg
---
> three turns after a user removed their card, i watched the agent tell them it was still on file. same session. the removal was sitting right there in the store, timestamped, plain as day. the agent reached past it, grabbed an older and more confident looking record, and ran with it. the user left and did not come back.

that bug has a shape. once you catch it you start seeing it in every agent you touch. i call it context pollution. the agent is carrying so much stale and contradictory context that it acts on something no longer true, and it does it with total confidence. a fact that got reversed last week still reads as current. two records disagree and nothing decides the winner. the detail that actually mattered is somewhere in two hundred thousand tokens of noise. old context leaks into answers where it has no business.

the whole industry reflex is to throw more window at this. keep the entire history in the prompt. let the model sort it out. it does not work. you handed the model more junk to weigh, at more cost per call, with the right answer buried in the middle carrying no flag that says pick me. a longer prompt is a bigger haystack. you did not fix the memory. you made it slower to be wrong.

so let me get specific about what breaks, because "just use rag" is the problem in a nicer shirt.

## what most people ship as memory

nearly every memory tool is three lines. embed the text. store the vector. at query time embed the question and hand back the closest vectors. semantic search. useful, real, and nowhere near memory. it is a similarity lookup, and similarity carries less weight than the pitch decks suggest.

here is the crack in one sentence. similarity tells you what a thing looks like. it stays quiet on whether that thing is relevant, whether it is still true, and why it happened. three separate questions. a nearest neighbor search fumbles all three, and it fumbles them quietly, which is the dangerous part. you find out in production.

take them one at a time.

## the nearest match is a coin flip

ask a store what you decided about pricing. the embedding pulls the chunks that read like that question. but the chunk that answers you usually reads nothing like it. the real decision might be a single line in a standup note, written as a flat statement, sharing zero vocabulary with your query. meanwhile five paragraphs that say pricing and page over and over rank higher, and not one holds the decision.

scale makes it worse, and not on a straight line. at a hundred memories the top hit is fine. at a hundred thousand it is a toss up between the true answer and a knot of near misses that share surface words. recall falls as the store grows. that is backwards for something called memory.

the sneaky version is the one that bites hardest. when nothing relevant exists, the search still returns something. it always coughs up the closest row, even at cosine 0.2, even when the honest reply is i have nothing for you. so the agent poses a question its memory cannot answer, catches whatever landed nearest, and reports it as fact. most confident nonsense in these systems starts here. the model is not making things up. the retrieval layer was never given permission to say i do not know. a similarity floor, a gap check between the top two hits, one flat "not confident" line. worth more than another point of recall.

## the cause sits four hops from the question

this is the failure that made me put the off-the-shelf stuff down.

why did the service fall over on friday. the true answer is a chain. it fell over because it ran out of memory. it ran out of memory because a background job leaked on every request. the job leaked because of a change that landed tuesday. tuesday is the cause. friday is the symptom. they sit four hops apart and share almost no words.

the lookup embeds your question, finds the record that reads most like it, and that record is the friday outage. the symptom. it hands back the thing you already knew and calls it done. the tuesday change, the actual root, is written so far from your phrasing that it never even makes the shortlist.

a flat pile of vectors has no chain to walk. it holds points and knows nothing about how any point connects to the next. it matches your words. it cannot reason from one fact to another. different operation entirely, and better embeddings do not close it, because the missing thing is structure.

i ran the numbers, because a claim like that means nothing without them. eight separate incidents, each a real chain from root to symptom, then buried under a couple hundred unrelated memories so it stayed honest. ask each symptom question, check whether the true root comes back. plain vector search, top hit, got none of the eight. give it the top three, still none. the root is phrased so unlike the symptom it never surfaces. walk the caused-by links on a graph instead, and it lands all eight, every run, in about eleven milliseconds. that gap is not incremental. one approach cannot do the task, the other does it cold.

## the diet coke problem

now the hardest thing in the field, wearing the costume of the easiest.

in january the user tells the agent they like diet coke. in may they say they do not like it anymore. today the agent should know they do not. trivial, on paper.

watch an embedding try. "i like diet coke" and "i don't like diet coke" sit about 0.87 cosine apart. very close. the word don't barely nudges the vector. that is not a knob you can turn, it is what an embedding is for. the model was trained to park sentences about the same topic near each other, and both of those are about diet coke. negation is a logic operator. cosine has never heard of logic. so ask does the user like diet coke and the store cannot separate the two, returns whichever landed a hair nearer, and holds no notion that one canceled the other.

better embeddings will not save you here. an embedding will never read don't reliably, so stop handing it the job. key the fact to a subject, the thing the fact is about. a newer fact on that subject supersedes the older one, flat and deterministic, no fuzzy match, no guessing. diet coke owns a slot. the may memory takes the slot. january moves to history and stays there.

keeping that history buys you something a flat store cannot sell at any size. you can ask what was true at some past moment. you can ask how a view changed. you watch the opinion move, january to may, like to gone, instead of only ever seeing the latest state. the history earns its keep. knowing a user moved cities is what makes "my old place" mean anything. a store that overwrites on update throws that out and calls it tidy.

same test. a batch of facts, each later reversed by an update, ask what holds now. plain vector search scores zero, because the stale and the current fact both look like the query and it has no way to choose. the subject-keyed version scores everything, because it stopped guessing and started reading a slot.

## forgetting is the feature

here is the part the field spent a while refusing to say out loud.

the pitch was always remember more. bigger store. bigger window. keep it all. more turned out to be worse. the same preference saved four slightly different ways. last month's decision parked next to this month's, both returned by search, both billed on every single call. the store bloats and recall rots right alongside it.

your own head does not run on keep-everything. you have already lost most of today. you hold what mattered and let the rest go, and the reason you can pull up anything useful is that every night your brain hauls out the trash and folds what survives into something cleaner. sleep is a compaction pass. i mean that literally, it is the function.

storage figured this out decades back. no serious engine reconciles at write time under load. it takes writes fast and compacts later, in the background, off the hot path. log structured stores run compaction. postgres runs vacuum. git garbage collects. agent memory shipped the fast write path, skipped the background pass, and then acted shocked when the store turned to sludge. across 2026 the major labs all rediscovered the same fix within a few months of each other, gave it different names, and under the names it is that missing compaction pass finally getting scheduled. it merges records that say one thing twice. it supersedes a fact when a newer one lands, so the current truth wins the next search. and it reads a cluster of small related memories and writes the bigger fact they add up to, keeping a pointer back to every source.

that third move is the one that earns the whole thing. you order thai eight fridays running. eight little records. a memory worth the name figured out weeks ago that you like thai and you have a friday habit, and it wrote that down. that is not lookup. that is the memory thinking about itself while nothing waits on it.

say it plain. a bigger pile loses. the memory that wins gets cleaner as it grows.

## a memory that works is a graph

stack all of that up and a specific shape falls out. a graph.

each memory is a node. text, an embedding for meaning, a timestamp, and the subject the fact is about. the links between nodes carry a type. this one was caused by that one. this one reverses that one. this one comes after that one in time. the links do the real work, because the links are what let the thing reason instead of match.

on that base you bolt the moves similarity cannot make. you answer why by walking caused-by links from a symptom down to the root. you answer what holds now by keying facts to subjects so a fresh fact retires the stale one, and you keep the stale one as history. you let it say i am not confident instead of shoving the nearest random row at you. you tie the same person or place across memories, a join a flat store simply cannot do. and you rank on more than one signal, because some days you do not want the semantically nearest memory, you want the one that literally contains the string error zx9q, and an embedding blurs exact tokens like ids and codes into paste. so you fuse a keyword score and an entity score with the vector using reciprocal rank fusion. take each item's rank under each signal, add one over k plus rank, sort. no weight tuning, no wrestling scores that live on different scales. it just works, which is why half the field quietly runs it.

## the whole engine is small

all of it fits in about four hundred lines. one local file. memories are rows. links are rows. vector search is a dot product. the causal walk is a loop over links. compaction is a merge and a summarize. no cluster. no cloud. nothing to boot up.

and the small size is the actual point, not a flex about tidy code. storage was never the hard part of memory. storage is a table in a database and it has been solved for forty years. the hard part was the shape. get the shape right and four hundred lines outrun a pile of vectors at any size, because the pile is missing the one thing that counts, the wiring of how facts relate. adding complexity is easy and everyone can do it. the judgment is spotting the single idea, that memory wants to be a graph, that makes most of the complexity vanish.

## when you actually need scale

people grab a vector database on day one and inherit a distributed systems problem they never had. a dot product over a few hundred thousand normalized vectors is a couple milliseconds of simd. you do not need an approximate index until you are well past that, and most personal or agent memory never gets close.

and the day you do scale, the naive path bites in a very specific spot. pgvector is the classic. you build an hnsw index like every tutorial swears by, then you add a tenant filter, and the planner weighs walking the index against scanning the filtered rows and picks the scan. your index sits at zero scans while every query runs an eight second sequential scan across a terabyte. not a bug. the planner did its job. vectors and relational rows have opposite access patterns and you crammed them into one table. at that point you split them, vectors into something built for vectors, relational data where it belongs. that is a ten-million-vector, live-multi-tenant problem though. it is not a reason to complicate your first thousand memories.

## what is still broken

i will not pretend this is finished, because the open edge is the interesting part and pretending is how you lose a reader who knows the material.

contradiction across different subjects is still hard. "i am vegan now" should quietly kill "i love steak", but on the surface those point at different things, and catching it reliably still wants a model in the loop, not a rule. tracking a person through change is shaky. my manager is alice, then alice left, then bob runs the team. a human never loses the thread. a system needs real entity resolution to hold it. whether a reversed fact should vanish or linger as history has no settled answer, keep the trail and you can ask what you used to believe, but you carry more weight. and compaction has a tension baked in, the summaries it writes are themselves new memories fighting for the same retrieval slots, so a system that consolidates too eagerly makes recall worse, and nobody has nailed the right cadence.

none of that means the approach is wrong. it means this is where the work is, and naming it honestly separates the people who understand the problem from the people selling a finished one. memory is not solved. the direction is clear. structure over piles. deliberate forgetting over hoarding. knowing why something happened and what still holds, past what merely looks similar.

the benchmark for the causal and temporal claims is public and it runs in about ten seconds. i would rather you not believe me. run it, and watch the standard approach post a zero on the two questions that actually decide whether an agent feels smart or feels broken.

next time i take the diet coke problem apart on its own, why an embedding is blind to don't and how a subject slot fixes it with no model at all. after that, why your memory should dream, and what the background compaction pass is really doing when it runs. each one reads on its own. pick whichever title pulls you ^^
