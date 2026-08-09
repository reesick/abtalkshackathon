# AI Influencer Discovery Sources --- Integration & Test Guide

## Mission

Upgrade the existing discovery layer in `agent/nodes/discover.py` so the
AI influencer can discover **actual daily signals**, not just company
press releases.

The goal is source diversity:

-   Product launches
-   Open-source projects
-   Research
-   Developer activity
-   AI news
-   Startups / funding
-   Practical AI tools
-   Builder commentary
-   Video / creator signals

**Important:** this task is ONLY about the discovery/source module.

Do **not** redesign the rest of the agent, scoring pipeline, content
generation, posting, memory, scheduling, or persona logic.

After implementing the source collectors, **test this module only**.

------------------------------------------------------------------------

# 1. Existing Discovery System

Current `agent/nodes/discover.py` already has:

### RSS

``` python
RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss",
    "https://blog.google/technology/ai/rss",
    "https://huggingface.co/blog/feed.xml",
]
```

### Hacker News

Current terms:

``` python
HN_QUERY_TERMS = [
    "LLM",
    "large language model",
    "AI agent",
    "open weights",
    "inference",
]
```

However, the current implementation only queries:

``` python
HN_QUERY_TERMS[:3]
```

So `"open weights"` and `"inference"` are currently unused.

### Reddit

Current:

``` python
REDDIT_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
]
```

The public `.json` endpoints have been returning HTTP 403, so Reddit
should **not** be a required dependency for this upgrade.

Do not spend the implementation task trying to bypass Reddit blocking.

------------------------------------------------------------------------

# 2. Target Source Architecture

The source layer should eventually look roughly like:

``` text
                    DISCOVERY
                       |
       +---------------+----------------+
       |               |                |
    PRODUCTS        BUILDERS         RESEARCH
       |               |                |
 Product Hunt       GitHub            arXiv
 TAAFT              HN                Hugging Face
 Futurepedia        YouTube           BAIR
                                        DeepMind
                                        Simon Willison
       |               |                |
       +---------------+----------------+
                       |
                     NEWS
                       |
        +--------------+--------------+
        |              |              |
    TechCrunch     VentureBeat     Ars
    Verge          MIT TR            Axios
    TNW
                       |
                 COMPANY SIGNALS
                       |
       OpenAI / Anthropic / Google
       Microsoft / AWS / NVIDIA
```

The important principle:

> **Do not treat every source as an RSS feed.**

Some sources have APIs, some have RSS, some have HTML pages, and some
should be treated as optional adapters.

------------------------------------------------------------------------

# 3. Source Priority

## Tier S --- Core

These should be implemented first.

  -----------------------------------------------------------------------
  Source                  Signal                  Integration
  ----------------------- ----------------------- -----------------------
  Product Hunt            New products / launches GraphQL API

  GitHub                  Open-source momentum    REST API + optional
                                                  Trending page

  Hacker News             Builder discussion /    Firebase API + Algolia
                          Show HN                 search

  Hugging Face            Papers / models /       Public pages/API where
                          Spaces                  appropriate

  Simon Willison          LLM tooling +           Atom
                          practitioner            
                          discoveries             

  TechCrunch AI           Startups / launches /   RSS
                          funding                 

  arXiv                   New research            RSS
  -----------------------------------------------------------------------

## Tier A --- Strong

  Source                  Signal                             Integration
  ----------------------- ---------------------------------- ------------------
  DeepMind                Frontier research                  RSS
  BAIR                    Academic AI research               RSS
  VentureBeat AI          Enterprise AI / infrastructure     RSS/page
  Ars Technica AI         Technical + industry news          RSS/page
  The Verge AI            Consumer AI / industry             RSS/page
  MIT Technology Review   High-quality technology analysis   RSS/page
  YouTube                 Creator / researcher signals       YouTube Data API
  Axios                   AI business / funding / deals      RSS/page

## Tier B --- Secondary

  Source                   Signal                              Integration
  ------------------------ ----------------------------------- -----------------
  Futurepedia              AI tools / workflows                Page/newsletter
  There's An AI For That   AI tool discovery                   Page/search
  AWS ML Blog              Product / technical announcements   RSS
  NVIDIA Blog              AI hardware / infrastructure        RSS
  Microsoft Research       Research                            RSS
  Google AI Blog           Research / product                  Existing RSS
  OpenAI News              Primary announcements               Existing RSS
  Anthropic News           Primary announcements               Existing RSS
  TNW                      General technology / startups       RSS/page

------------------------------------------------------------------------

# 4. Product Hunt

## Why

Product Hunt is one of the most important additions because it answers:

> What AI products are people actually launching today?

That is substantially more useful for an influencer than simply reading
company announcement feeds.

## Integration

Use the **Product Hunt GraphQL API v2**.

Official API documentation:

https://api.producthunt.com/v2/docs

Do NOT scrape Product Hunt if the API can provide the required fields.

The API requires credentials. Keep them in environment variables.

Suggested:

``` env
PRODUCT_HUNT_API_TOKEN=...
```

Never hard-code the token.

## Collector

Create something along the lines of:

``` python
async def _fetch_product_hunt(limit: int = 10) -> list[dict]:
    ...
```

The exact GraphQL query should be based on the current Product Hunt API
documentation.

Prefer fields such as:

``` text
id
name
tagline
description
url
createdAt
featuredAt
votesCount
commentsCount
topics
maker information
```

Only request fields that are actually supported by the current API.

## Normalised output

Convert Product Hunt results into the same internal candidate shape used
by the existing discovery module.

Suggested fields:

``` python
{
    "source": "product_hunt",
    "source_type": "product",
    "title": ...,
    "summary": ...,
    "url": ...,
    "published_at": ...,
    "metadata": {
        "votes": ...,
        "comments": ...,
        "topics": [...],
    }
}
```

Do not break the existing candidate schema if one already exists.

## Filtering

Prefer AI-relevant products.

Useful topic/keyword signals:

``` text
AI
artificial intelligence
LLM
agent
agents
generative AI
image
video
voice
speech
coding
developer tools
automation
RAG
machine learning
```

Do not blindly reject a product just because the title does not contain
"AI". Product Hunt topic metadata may identify relevant products.

------------------------------------------------------------------------

# 5. GitHub

## Why

GitHub is one of the strongest sources because **developer activity is a
real signal**.

A repository gaining hundreds or thousands of stars rapidly is often
more interesting than another corporate blog post.

## Official REST API

Use:

https://docs.github.com/en/rest

The GitHub REST API has feed/activity endpoints, but there is no
official API endpoint called "Trending".

Therefore:

### Preferred

Use GitHub API search to detect momentum.

Potential strategy:

``` text
created / pushed recently
language / topic filters
stars
forks
updated_at
```

For example, query recently created or recently pushed repositories
containing:

``` text
AI
LLM
agent
RAG
multimodal
inference
vision
speech
generative AI
```

Then calculate a rough momentum signal from:

``` text
stars
forks
repository age
recent update activity
```

### Optional

If you explicitly want GitHub's human-facing Trending page:

``` text
https://github.com/trending
```

Treat HTML scraping as a separate optional collector.

Do not make the whole discovery pipeline dependent on scraping it.

## Suggested collector

``` python
async def _fetch_github_ai_repos(limit: int = 20) -> list[dict]:
    ...
```

## Normalised metadata

``` python
{
    "source": "github",
    "source_type": "repository",
    "title": repo["full_name"],
    "summary": repo["description"],
    "url": repo["html_url"],
    "published_at": repo["created_at"],
    "metadata": {
        "stars": repo["stargazers_count"],
        "forks": repo["forks_count"],
        "language": repo["language"],
        "topics": repo.get("topics", []),
    }
}
```

Do not invent `stars_today` unless it is actually calculated from
historical observations.

------------------------------------------------------------------------

# 6. Hacker News

The current HN integration is useful but should be improved.

Official Firebase API:

https://github.com/HackerNews/API

Keep Algolia if the current implementation is useful for text search.

Add the unused query terms:

``` python
"open weights"
"inference"
```

Also consider:

``` python
"AI coding"
"AI agent"
"agentic"
"RAG"
"multimodal"
"open source AI"
"local LLM"
"reasoning model"
```

Do not explode the number of API requests.

Keep a sensible limit.

Also give special treatment to:

``` text
Show HN
Ask HN
```

because these often produce stronger original discussion than ordinary
links.

------------------------------------------------------------------------

# 7. Hugging Face

Hugging Face should be treated as an ecosystem source, not merely a blog
feed.

Official platform:

https://huggingface.co/

## Trending Papers

Use:

https://huggingface.co/papers/trending

This exposes daily / weekly / monthly trending papers.

The current page provides paper popularity signals such as:

``` text
upvotes
GitHub activity
paper metadata
```

Use the public page or supported API/data source only if it is actually
accessible.

Do not invent an undocumented endpoint.

## Hugging Face Spaces

Also consider:

https://huggingface.co/spaces

This is useful for discovering new AI applications:

-   image generation
-   video generation
-   speech
-   OCR
-   agents
-   3D
-   code generation
-   document analysis

Again, verify the actual endpoint/response before implementing.

------------------------------------------------------------------------

# 8. arXiv

Keep:

``` text
http://export.arxiv.org/rss/cs.LG
http://export.arxiv.org/rss/cs.CL
```

Add these as RSS collectors.

Important:

arXiv has high volume.

Do NOT simply dump hundreds of papers into downstream processing.

Use:

``` python
feed.entries[:N]
```

and/or a date filter.

Prioritise topics around:

``` text
LLM
agents
reasoning
RAG
multimodal
vision-language
speech
inference
training
evaluation
AI safety
```

------------------------------------------------------------------------

# 9. Simon Willison

Use:

``` text
https://simonwillison.net/atom/everything/
```

This is a very strong practitioner source.

Why it matters:

-   LLM experiments
-   developer tooling
-   prompt injection
-   new APIs
-   model behaviour
-   practical discoveries
-   open-source tooling

Use Atom parsing through the existing `feedparser` path if available.

Do not require a new parser library if `feedparser` already handles it.

------------------------------------------------------------------------

# 10. TechCrunch AI

TechCrunch has an AI category:

https://techcrunch.com/category/artificial-intelligence/

TechCrunch explicitly provides RSS support.

Use the official RSS feed where available rather than scraping article
pages.

Likely category feed pattern:

``` text
https://techcrunch.com/category/artificial-intelligence/feed/
```

**Verify this endpoint during implementation.**

Do not blindly assume the URL works.

TechCrunch is especially useful for:

``` text
funding
acquisitions
startups
new products
AI companies
business moves
```

The current AI category is active and covers generative AI, LLMs,
image/video, speech and related AI companies.

------------------------------------------------------------------------

# 11. DeepMind

Use:

``` text
https://deepmind.google/blog/rss.xml
```

Use this as a **primary research source**, not a hype detector.

Good for:

-   new research
-   robotics
-   multimodal models
-   scientific AI
-   agents
-   reinforcement learning

------------------------------------------------------------------------

# 12. BAIR

Use:

``` text
https://bair.berkeley.edu/blog/feed.xml
```

Good for technical research and mechanisms.

Prioritise:

``` text
new method
new architecture
new evaluation
new capability
new training technique
```

Down-rank routine academic announcements.

------------------------------------------------------------------------

# 13. VentureBeat

Use the AI section:

https://venturebeat.com/category/ai/

This source is useful for:

-   enterprise AI
-   AI infrastructure
-   agents
-   model deployments
-   enterprise adoption

Verify the current RSS endpoint before wiring it.

If no reliable RSS exists, use a page collector only if the existing
architecture supports safe HTTP fetching and parsing.

------------------------------------------------------------------------

# 14. Ars Technica

Use:

https://arstechnica.com/ai/

Useful for:

-   technical analysis
-   AI security
-   regulation
-   hardware
-   copyright
-   failures
-   real-world consequences

This should be treated as a news/article source, not a raw announcement
source.

------------------------------------------------------------------------

# 15. The Verge

Use:

https://www.theverge.com/ai-artificial-intelligence

Good for:

-   consumer AI
-   major launches
-   product behaviour
-   AI industry developments
-   public reaction

Verify the current feed endpoint before implementing.

------------------------------------------------------------------------

# 16. MIT Technology Review

Use:

https://www.technologyreview.com/topic/artificial-intelligence/

Useful for higher-quality analysis.

Because it is broader than pure ML, apply an AI relevance filter.

Do not ingest everything.

------------------------------------------------------------------------

# 17. Axios

Use:

https://www.axios.com/technology

Useful for:

-   AI companies
-   deals
-   funding
-   business strategy
-   policy
-   industry shifts

Verify the current feed/page endpoint before implementation.

------------------------------------------------------------------------

# 18. YouTube

YouTube is useful for monitoring selected researchers/builders/AI
creators.

Official API docs:

https://developers.google.com/youtube/v3/docs

Use the official YouTube Data API where possible.

Recommended workflow:

``` text
curated channel IDs
        ↓
YouTube API
        ↓
new videos
        ↓
title + description + published_at
        ↓
candidate
```

Do NOT attempt to search all of YouTube every few minutes.

Maintain a small curated channel list.

Potential initial channels:

``` text
Andrej Karpathy
Yannic Kilcher
Two Minute Papers
AI Explained
Latent Space
Matt Wolfe
Fireship
```

**Do not hard-code channel IDs from memory.**

Resolve/verify each channel ID during setup.

The YouTube API supports channel/video retrieval and playlist-based
retrieval.

------------------------------------------------------------------------

# 19. Futurepedia

Official:

https://www.futurepedia.io/

Futurepedia currently describes itself as an AI tool directory with
thousands of curated tools.

Its AI tools categories include:

``` text
AI agents
AI image
AI video
AI audio
automation
marketing
coding
productivity
```

Use it as a secondary discovery source.

Do not make scraping the homepage a critical dependency.

If there is no stable official API/feed, implement it as:

``` text
OPTIONAL
```

and fail gracefully.

------------------------------------------------------------------------

# 20. There's An AI For That

Use:

https://theresanaiforthat.com/

This is useful for discovering AI products and use cases.

Again:

**Do not assume an undocumented API exists.**

First verify:

1.  official API
2.  RSS/feed
3.  stable page
4.  only then HTML extraction

If no reliable machine-readable source exists, leave it as an optional
adapter rather than introducing brittle scraping into the core pipeline.

------------------------------------------------------------------------

# 21. AWS Machine Learning Blog

Existing verified candidate:

``` text
https://aws.amazon.com/blogs/machine-learning/feed/
```

Useful for:

-   inference
-   cloud ML
-   enterprise AI
-   AWS AI tooling

Down-rank routine product announcements.

------------------------------------------------------------------------

# 22. NVIDIA

Use:

``` text
https://blogs.nvidia.com/feed/
```

Useful for:

-   GPUs
-   inference
-   AI infrastructure
-   robotics
-   CUDA ecosystem
-   model optimisation

Because the blog is not AI-only, add an AI relevance filter.

------------------------------------------------------------------------

# 23. Microsoft Research

Use:

``` text
https://www.microsoft.com/en-us/research/feed/
```

Good research source.

Prioritise:

``` text
LLMs
agents
reasoning
multimodal
AI systems
computer vision
speech
```

------------------------------------------------------------------------

# 24. Existing OpenAI / Anthropic / Google / HF Sources

Keep the current sources:

``` text
https://openai.com/news/rss.xml
https://www.anthropic.com/news/rss
https://blog.google/technology/ai/rss
https://huggingface.co/blog/feed.xml
```

But classify them as:

``` text
primary_company_source
```

rather than giving them the same discovery weight as independent
sources.

The agent should be able to recognise:

``` text
company announces X
```

versus:

``` text
independent source discovers X
```

------------------------------------------------------------------------

# 25. Reddit

Do not make Reddit part of the required implementation.

Current public `.json` requests are returning 403.

Do not implement:

-   proxy bypasses
-   UA tricks intended to evade blocking
-   scraping workarounds

If Reddit is revisited later, use the official API/OAuth route.

For this task:

``` text
REDDIT = OPTIONAL / DISABLED
```

------------------------------------------------------------------------

# 26. Normalised Candidate Schema

All source adapters should produce the existing candidate structure.

If the project does not already have a strict schema, use a shape close
to:

``` python
{
    "source": "product_hunt",
    "source_type": "product",
    "title": "...",
    "summary": "...",
    "url": "...",
    "published_at": "...",
    "metadata": {
        # source-specific fields
    }
}
```

Do not create a second incompatible candidate format.

------------------------------------------------------------------------

# 27. Source Adapter Design

Prefer small isolated functions:

``` python
async def _fetch_rss(...):
    ...

async def _fetch_hn(...):
    ...

async def _fetch_product_hunt(...):
    ...

async def _fetch_github(...):
    ...

async def _fetch_huggingface(...):
    ...

async def _fetch_youtube(...):
    ...
```

Then combine them in the existing discovery orchestration.

Do not rewrite unrelated parts of the agent.

Each collector should:

1.  fetch
2.  parse
3.  normalise
4.  return candidates
5.  fail gracefully

A broken optional source must not kill the whole discovery run.

------------------------------------------------------------------------

# 28. Error Handling

Every external source can fail.

Use source-level isolation:

``` python
try:
    candidates = await _fetch_source()
except Exception as exc:
    logger.warning("Source failed: %s", exc)
    candidates = []
```

Do not silently swallow all errors.

The current Reddit behaviour is a bad example because failures
disappear.

At minimum log:

``` text
source
HTTP status
exception
number of candidates
```

Never log:

``` text
API tokens
Authorization headers
secrets
```

------------------------------------------------------------------------

# 29. HTTP Requirements

Use the project's existing HTTP client if one exists.

Do not introduce a second HTTP stack unnecessarily.

For every source:

-   sensible timeout
-   redirect handling
-   HTTP status validation
-   user agent where appropriate
-   JSON/XML/content-type validation
-   pagination where needed
-   rate limiting where required

Do not create a huge global timeout.

------------------------------------------------------------------------

# 30. API Keys

Use environment variables.

Potential:

``` env
PRODUCT_HUNT_API_TOKEN=
GITHUB_TOKEN=
YOUTUBE_API_KEY=
```

Only add variables for sources that actually require them.

Do not commit credentials.

If credentials are missing:

``` text
source disabled
```

not:

``` text
entire discovery pipeline crashes
```

------------------------------------------------------------------------

# 31. Deduplication

Different sources may report the same event.

For example:

``` text
TechCrunch → AI startup raises $100M
HN → same startup article
Axios → same funding round
```

The source layer should expose enough metadata for the existing
deduplication stage to merge them.

At minimum preserve:

``` text
canonical URL
title
published_at
source
```

Do not implement a giant new deduplication system as part of this task
unless one is already missing and the current module genuinely requires
it.

------------------------------------------------------------------------

# 32. Source Quality

Add a source classification:

``` text
primary
independent
community
research
product
```

Suggested:

  Source               Class
  -------------------- --------------------------
  OpenAI               primary
  Anthropic            primary
  Google AI            primary
  DeepMind             primary/research
  Microsoft Research   research
  arXiv                research
  BAIR                 research
  Hugging Face         community/research
  GitHub               community
  Hacker News          community
  Product Hunt         product
  TechCrunch           independent/news
  Ars                  independent/news
  Verge                independent/news
  Simon Willison       independent/practitioner
  YouTube              community
  Futurepedia          product
  TAAFT                product

------------------------------------------------------------------------

# 33. Testing Requirements

## VERY IMPORTANT

After implementation:

### Test ONLY the discovery/source module.

Do not run:

-   content generation
-   posting
-   social media publishing
-   scheduling
-   unrelated agent nodes
-   expensive model calls

The goal is to prove the source layer works.

------------------------------------------------------------------------

# 34. Required Test

Create or use a focused test such as:

``` text
tests/test_discovery_sources.py
```

or whatever test structure the repository already uses.

Test:

### A. Existing RSS

Verify:

``` text
OpenAI
Anthropic
Google AI
Hugging Face
```

### B. New RSS

Verify:

``` text
arXiv cs.LG
arXiv cs.CL
BAIR
DeepMind
Simon Willison
AWS ML
NVIDIA
Microsoft Research
TechCrunch
```

### C. HN

Verify:

``` text
LLM
large language model
AI agent
open weights
inference
```

### D. Product Hunt

If token exists:

``` text
request succeeds
GraphQL response parses
at least one candidate is returned
candidate schema is correct
```

If token does not exist:

``` text
collector skips gracefully
test reports source as unavailable/configuration missing
```

Do not fake successful API results.

### E. GitHub

Verify:

``` text
request succeeds
repositories parse
candidate schema is correct
```

Use an unauthenticated request if no token exists, subject to GitHub
rate limits.

### F. Hugging Face

Verify:

``` text
Trending Papers page/data can be fetched
paper title/url/date parse correctly
```

Do not invent an API endpoint.

### G. YouTube

Only test if API key is configured.

Verify:

``` text
channel lookup
video retrieval
normalisation
```

If key is absent, skip gracefully.

### H. Optional sources

Futurepedia and There's An AI For That should be tested only if a stable
integration path was verified.

------------------------------------------------------------------------

# 35. Test Output

The focused test should print a compact report like:

``` text
DISCOVERY SOURCE TEST
=====================

OpenAI RSS          PASS   5 candidates
Anthropic RSS       PASS   5 candidates
Google AI RSS       PASS   5 candidates
Hugging Face RSS    PASS   5 candidates

arXiv cs.LG         PASS   5 candidates
arXiv cs.CL         PASS   5 candidates
BAIR                PASS   5 candidates
DeepMind            PASS   5 candidates
Simon Willison      PASS   5 candidates
TechCrunch AI       PASS   5 candidates
AWS ML              PASS   5 candidates
NVIDIA              PASS   5 candidates
Microsoft Research  PASS   5 candidates

Hacker News         PASS   20 candidates
GitHub              PASS   20 candidates
Hugging Face Papers PASS   10 candidates

Product Hunt        PASS   10 candidates
YouTube             SKIP   API key not configured

Reddit              SKIP   intentionally disabled

TOTAL
-----
PASS: ...
SKIP: ...
FAIL: ...
```

Do not mark a source PASS if it returned zero because of an
implementation error.

------------------------------------------------------------------------

# 36. Important: Real Network Test

This is a source-integration task.

Do not rely exclusively on mocks.

The test should include a small **live smoke test** against the real
endpoints.

Mocks can be added separately for unit tests, but they do not prove
that:

``` text
URL still works
API schema still works
RSS structure still works
authentication works
parsing works
```

For the live smoke test:

-   keep limits small
-   use timeouts
-   avoid excessive API calls
-   do not publish anything
-   do not call LLMs

------------------------------------------------------------------------

# 37. Do Not Over-Engineer

Do NOT:

-   rewrite `discover.py` from scratch
-   refactor unrelated modules
-   change the agent persona
-   change the post-generation pipeline
-   change database schema unless absolutely required
-   introduce Celery/Redis/etc.
-   add a new framework
-   build a crawler
-   scrape sites unnecessarily
-   bypass anti-bot protection
-   add Reddit workarounds
-   create fake API credentials
-   fake successful tests

The task is:

> **Add/upgrade discovery sources and prove the discovery module
> works.**

------------------------------------------------------------------------

# 38. Definition of Done

This task is complete when:

-   [ ] Product Hunt adapter exists or is cleanly disabled when
    credentials are absent
-   [ ] GitHub discovery exists
-   [ ] HN queries include all relevant configured terms
-   [ ] Hugging Face trending-paper discovery exists
-   [ ] arXiv cs.LG is wired
-   [ ] arXiv cs.CL is wired
-   [ ] BAIR is wired
-   [ ] DeepMind is wired
-   [ ] Simon Willison is wired
-   [ ] TechCrunch AI is wired
-   [ ] AWS ML is wired
-   [ ] NVIDIA is wired
-   [ ] Microsoft Research is wired
-   [ ] Existing OpenAI/Anthropic/Google/HF sources remain working
-   [ ] Optional YouTube adapter is added if credentials/configuration
    are available
-   [ ] Futurepedia/TAAFT are treated as optional unless a stable
    machine-readable integration is verified
-   [ ] Reddit is not required
-   [ ] All candidates use the existing normalised schema
-   [ ] Source failures do not kill the whole discovery run
-   [ ] Secrets are environment variables
-   [ ] Focused source tests exist
-   [ ] Live source smoke test has been run
-   [ ] No downstream content generation/posting was executed

------------------------------------------------------------------------

# 39. Final Instruction to the Coding Agent

**Implement this now.**

First inspect the existing discovery code and its candidate schema.

Then integrate the sources above using the least invasive approach
possible.

For every source that needs a URL/API endpoint, **verify the current
endpoint/documentation before coding it**. Do not rely on guessed URLs.

Use the existing project dependencies where possible.

After implementation, run **ONLY the discovery/source tests** and a
small live smoke test.

Report:

``` text
1. Files changed
2. Sources added
3. Sources skipped and why
4. Test results
5. Live endpoint results
6. Any API keys required
7. Any source that needs future work
```

Do not proceed into content generation or publishing.

------------------------------------------------------------------------

# Reference Links

## APIs / official documentation

-   Product Hunt API v2: https://api.producthunt.com/v2/docs
-   GitHub REST API: https://docs.github.com/en/rest
-   GitHub feeds: https://docs.github.com/en/rest/activity/feeds
-   Hacker News API: https://github.com/HackerNews/API
-   YouTube Data API: https://developers.google.com/youtube/v3/docs

## Discovery sources

-   Product Hunt: https://www.producthunt.com/
-   GitHub Trending: https://github.com/trending
-   Hugging Face: https://huggingface.co/
-   Hugging Face Trending Papers: https://huggingface.co/papers/trending
-   Hugging Face Spaces: https://huggingface.co/spaces
-   Futurepedia: https://www.futurepedia.io/
-   There's An AI For That: https://theresanaiforthat.com/

## Research / practitioner

-   arXiv cs.LG RSS: http://export.arxiv.org/rss/cs.LG
-   arXiv cs.CL RSS: http://export.arxiv.org/rss/cs.CL
-   BAIR: https://bair.berkeley.edu/blog/feed.xml
-   DeepMind: https://deepmind.google/blog/rss.xml
-   Simon Willison: https://simonwillison.net/atom/everything/

## News

-   TechCrunch AI:
    https://techcrunch.com/category/artificial-intelligence/
-   VentureBeat AI: https://venturebeat.com/category/ai/
-   Ars Technica AI: https://arstechnica.com/ai/
-   The Verge AI: https://www.theverge.com/ai-artificial-intelligence
-   MIT Technology Review AI:
    https://www.technologyreview.com/topic/artificial-intelligence/
-   Axios Technology: https://www.axios.com/technology
-   The Next Web: https://thenextweb.com/latest

## Company / technical sources

-   AWS Machine Learning Blog:
    https://aws.amazon.com/blogs/machine-learning/feed/
-   NVIDIA Blog: https://blogs.nvidia.com/feed/
-   Microsoft Research: https://www.microsoft.com/en-us/research/feed/
-   OpenAI News: https://openai.com/news/rss.xml
-   Anthropic News: https://www.anthropic.com/news/rss
-   Google AI Blog: https://blog.google/technology/ai/rss
-   Hugging Face Blog: https://huggingface.co/blog/feed.xml

------------------------------------------------------------------------

## Research notes

The source selection was checked against current web-accessible
documentation/pages before this guide was produced.

Product Hunt's current API documentation describes the v2 API; Product
Hunt API integrations use GraphQL. Hugging Face currently exposes
Trending Papers with daily/weekly/monthly views and popularity signals.
GitHub provides official REST APIs and feed endpoints, but GitHub
Trending itself is a website rather than a documented first-party
"Trending API". YouTube provides the official Data API for channel/video
retrieval. TechCrunch explicitly provides RSS feeds for use in
applications.

When an official machine-readable interface is unavailable, **verify the
current page/feed before implementing** rather than guessing or
introducing brittle scraping.
