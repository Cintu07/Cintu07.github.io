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

## building and deploying

```
pip install -r requirements.txt
python build.py
```

that writes the site to `dist/`. pushing to `main` runs `.github/workflows/pages.yml`, which does the same build and deploys it, so only the sources live in git. a new file in `content/posts/` is a new post a minute after the push.

set in [et book](https://github.com/edwardtufte/et-book), mit licensed. no javascript on the site.
