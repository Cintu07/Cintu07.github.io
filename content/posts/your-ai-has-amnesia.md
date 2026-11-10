---
title: your ai has amnesia, and a bigger context window will not fix it
date: 2026-08-10
description: three turns after a user removed their card, i watched the agent tell them it was still on file. same session.
tags: AI Agents, Memory, Machine Learning
cover: /assets/img/your-ai-has-amnesia-cover.jpg
---
a user removed their card, and three turns later, in the same session, the agent told them the card was still on file. the removal was in the memory store with a timestamp on it. the agent passed over it, picked an older record that looked more certain, and answered from that. the user left and didn't come back.

i call this context pollution. the agent carries so much old and contradictory context that it acts on something that stopped being true, and it does so with complete confidence. a fact reversed last week still reads as current, two records disagree with nothing to decide between them, and the one detail that mattered is buried somewhere in two hundred thousand tokens. most agents do it.

the usual response is a bigger context window. put the whole history in the prompt and let the model work it out. it doesn't help. the model now has more stale material to weigh, every call costs more, and the right answer is still somewhere in the middle with nothing marking it as the current one. the memory isn't any better. it's just slower to be wrong.

retrieval with embeddings, the usual next suggestion, has the same problem in a different place.

## what most memory tools are

nearly every memory tool works the same way. embed the text, store the vector, and at question time embed the question and return the nearest vectors. that's semantic search. it's useful, and it isn't memory. it's a similarity lookup.

similarity tells you what a piece of text looks like. it says nothing about whether the text is relevant, whether it's still true, or why the thing in it happened. nearest-neighbour search gets each of those wrong, and it gets them wrong without any sign that it has, so you find out in production.

## the nearest match is often the wrong one

ask a memory store what was decided about pricing. the embedding finds chunks that read like the question, but the chunk with the answer often reads nothing like it. the decision might be one flat line in a standup note that shares no words with the query, while five paragraphs that keep saying "pricing" rank above it and none of them contain the decision.

it gets worse as the store grows. at a hundred memories the top hit is usually fine. at a hundred thousand, the true answer is competing with a crowd of near misses that share surface words, and recall falls as the store gets bigger, which is the opposite of what memory should do.

the version that causes the most damage is when there's nothing relevant at all. the search still returns its closest row, even at a cosine of 0.2, when the right reply is that it has nothing. the agent asks a question its memory can't answer, gets back whatever was nearest, and states it as fact. a lot of confident nonsense in these systems starts here. the model isn't inventing it. the retrieval layer was never allowed to say it doesn't know. a minimum similarity, a check on the gap between the top two results, and a plain "not confident" answer would be worth more than another point of recall.

## the cause is four steps from the question

this is the failure that made me stop using the usual tools.

why did the service go down on friday? because it ran out of memory. it ran out of memory because a background job leaked on every request, and the job leaked because of a change that went in on tuesday. tuesday is the cause and friday is the symptom, four steps apart, with almost no words in common.

the lookup embeds the question, finds the record that reads most like it, and returns the friday outage, which is the thing you already knew. the tuesday change is worded so differently from the question that it never reaches the shortlist.

a flat set of vectors has no chain to follow. it holds points and knows nothing about how one connects to another. it can match words, and it can't go from one fact to the fact that caused it. better embeddings don't change that, because what's missing is structure.

i measured it. i took eight separate incidents, each a real chain from cause to symptom, and buried them among a couple of hundred unrelated memories. then i asked each symptom question and checked whether the real cause came back. plain vector search found none of the eight as the top result, and none in the top three either, because the cause is worded so unlike the symptom. following caused-by links in a graph found all eight, every run, in about eleven milliseconds. that's the difference between an approach that can't do the task and one that can.

## the diet coke problem

this looks like the easiest case and is one of the hardest.

in january the user tells the agent they like diet coke. in may they say they don't anymore. today the agent should know they don't.

"i like diet coke" and "i don't like diet coke" have a cosine similarity of about 0.87. the word "don't" barely moves the vector. that isn't a setting you can change. an embedding is trained to put sentences about the same topic near each other, and both sentences are about diet coke. negation is logic, and cosine similarity has no logic in it. ask whether the user likes diet coke and the store can't tell the two apart. it returns whichever happened to land nearer, with no idea that one cancelled the other.

a better embedding won't fix this, because no embedding reads "don't" reliably, so it shouldn't be given the job. key each fact to its subject, the thing it's about. a newer fact on the same subject replaces the older one, by a fixed rule with no fuzzy matching. diet coke has a slot. may's fact takes the slot and january's moves to history.

keeping the history gives you something a flat store can't. you can ask what was true at some earlier time, and you can see how something changed, liking it in january and not in may, instead of only ever seeing the latest state. knowing the user moved cities is what makes "my old place" mean anything, and a store that overwrites on every update throws that away.

i ran the same kind of test. a batch of facts, each later reversed, and the question was what's true now. plain vector search scored zero, because the old fact and the new one both look like the question and it has no way to choose. the version keyed by subject got all of them, because it reads a slot instead of guessing.

## forgetting is part of it

the pitch for memory has been to remember more, with a bigger store and a bigger window. more turned out to be worse. the same preference gets saved four slightly different ways. last month's decision sits next to this month's, both come back from search, and both are paid for on every call. the store grows and recall gets worse with it.

people don't keep everything either. most of today is already gone for you. you keep what mattered, and part of why you can recall anything useful is that sleep clears out the rest and folds what's left into something tidier.

storage engines learned this decades ago. none of them reconcile everything at write time under load. they take writes quickly and clean up later in the background. log-structured stores compact, postgres vacuums, git garbage-collects. agent memory built the fast write path, skipped the background pass, and was surprised when the store turned to sludge. during 2026 the major labs arrived at the same fix within a few months of each other, under different names. it's that missing cleanup pass, now scheduled. it merges records that say the same thing twice. it replaces a fact when a newer one arrives, so the current one wins the next search. and it reads a cluster of small related memories and writes down the larger fact they add up to, with a pointer back to each source.

that last step is the one that matters most. you order thai eight fridays in a row, which is eight small records. a memory system that works would have worked out weeks ago that you like thai and have a friday habit, and written that down. that's the memory summarising itself while nobody is waiting on it.

a store that only grows gets worse. the one that works gets tidier as it grows.

## the shape is a graph

put all of that together and you get a graph.

each memory is a node with its text, an embedding for meaning, a timestamp, and the subject it's about. the links between nodes have types, so one memory can be caused by another, reverse another, or come after another in time. the links matter most, because they're what let the system follow reasoning instead of matching words.

on top of that you can do what similarity can't. following caused-by links from a symptom to its cause answers "why". keying facts to subjects answers "what's true now", because a newer fact retires the older one and the older one stays as history. the system is allowed to say it isn't confident instead of returning the nearest random row, and the same person or place gets connected across memories, a join a flat store can't do.

and you rank on more than one signal. sometimes you don't want the memory nearest in meaning, you want the one that contains the exact string `error zx9q`, and embeddings blur ids and codes together. so you combine a keyword score and an entity score with the vector score using reciprocal rank fusion. each item gets one over (k plus its rank) under each signal, the results are added and sorted, and nothing needs tuning, because the different scores never have to be put on the same scale. that's a big part of why so many systems use it.

## the engine is small

all of this fits in about four hundred lines and one local file. memories are rows and links are rows. vector search is a dot product, the causal walk is a loop over links, and the cleanup pass is a merge followed by a summary. there's no cluster or cloud service and nothing to start up.

the size says something about the problem. storing things was never the hard part, since a table in a database has handled that for forty years. the hard part was the shape. with the shape right, four hundred lines do better than a pile of vectors of any size, because the pile is missing the one thing that counts, how the facts relate to each other. adding complexity is easy. noticing the one idea, that memory wants to be a graph, removes most of the complexity in the first place.

## when you do need scale

people often start with a vector database and inherit a distributed system they didn't need. a dot product over a few hundred thousand normalised vectors takes a couple of milliseconds with simd. you don't need an approximate index until well past that, and most personal or agent memory never gets there.

when you do get there, the simple path tends to break in one specific place, and pgvector is the usual example. you build an hnsw index the way the tutorials say, add a filter on tenant, and the query planner decides scanning the filtered rows is cheaper than walking the index. the index shows zero scans while every query does an eight-second sequential scan over a terabyte. it isn't a bug. the planner did its job. vectors and relational rows want opposite access patterns, and they were put in one table. at that point you split them, with vectors in something built for vectors and the relational data where it belongs. but that's a problem for ten million vectors and live multi-tenancy, not for your first thousand memories.

## what's still broken

contradictions across different subjects are still hard. "i'm vegan now" should retire "i love steak", but on the surface they're about different things, and catching that reliably still needs a model in the loop instead of a rule.

following a person through change is shaky too. my manager is alice, then alice leaves, then bob runs the team. people never lose that thread, and a system needs proper entity resolution to keep it.

there's no settled answer on whether a reversed fact should disappear or stay as history. keeping it lets you ask what you used to believe, and it costs space and retrieval time.

and the cleanup pass works against itself a little. the summaries it writes are new memories competing for the same retrieval slots, so a system that consolidates too eagerly ends up with worse recall, and nobody has found the right rhythm for it yet.

the benchmark behind the cause-chain and diet coke numbers is public and runs in about ten seconds.
