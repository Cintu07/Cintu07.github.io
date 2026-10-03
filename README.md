# pawan

my blog, at https://cintu07.github.io. long posts, the papers i implement, and books when there is one.

## writing a post

drop a markdown file in `content/posts/`:

```
---
title: the title
date: 2026-10-03
description: one line for the list and the link preview
tags: go, systems
cover: /assets/img/optional-cover.jpg
---
```

a leading `>` quote becomes the standfirst under the title. without one, the description is used. put images in `assets/img/` and link them as `/assets/img/name.png`.

## papers and books

`content/papers.json` and `content/books.json`. a book has `title`, `blurb`, and optionally `status`, `year`, `url`, `linkText`. the books page and its nav link appear once the list is not empty.

## building

```
pip install markdown pygments
python build.py
```

the generated pages sit in the repo root because that is what github pages serves. commit them with the source.

set in [fraunces](https://github.com/undercasetype/Fraunces) and [geist mono](https://github.com/vercel/geist-font), both under the SIL open font license.
