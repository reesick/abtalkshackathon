# Discovery Sources — Working Notes

Status of every source currently wired into `agent/nodes/discover.py`, plus
verified candidates to add. Checked for real via `curl` on 2026-08-09 — not
guessed from memory. Anything marked ❌ is a genuine current failure, not
speculation.

---

## 1. Currently wired in (`agent/nodes/discover.py`)

### RSS feeds (`RSS_FEEDS`)

| Feed | URL | Status |
|---|---|---|
| OpenAI News | `https://openai.com/news/rss.xml` | ✅ working (seen in every run) |
| Anthropic News | `https://www.anthropic.com/news/rss` | ✅ working |
| Google AI Blog | `https://blog.google/technology/ai/rss` | ✅ working |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` | ✅ working |

Each feed pulls the 5 most recent entries (`feed.entries[:5]`).

### Hacker News (Algolia search API)

Query terms in `HN_QUERY_TERMS`, but **only the first 3 are actually used**
(`HN_QUERY_TERMS[:3]` in `_fetch_hn`) — `"open weights"` and `"inference"`
are defined but never queried right now:

```python
HN_QUERY_TERMS = ["LLM", "large language model", "AI agent", "open weights", "inference"]
```

✅ Working — `hn.algolia.com/api/v1/search_by_date`, no auth needed, 5 hits
per term, sorted by date.

### Reddit (`.json` endpoints, no auth)

```python
REDDIT_SUBREDDITS = ["MachineLearning", "LocalLLaMA"]
```

❌ **Currently broken** — confirmed via direct `curl` just now:
```
GET https://www.reddit.com/r/MachineLearning/hot.json?limit=10 → 403
GET https://www.reddit.com/r/LocalLLaMA/hot.json?limit=10 → 403
```
This is why Reddit candidates have never appeared in any run this session —
not a coincidence, a real block. Reddit is rate-limiting/blocking the
generic `User-Agent: abtalks-agent/1.0` and/or the requesting IP. `discover.py`
swallows the exception silently (`except Exception: continue`), so this fails
quiet — worth knowing before assuming Reddit is contributing anything right now.

**Possible fixes, not yet applied:**
- Rotate/randomize `User-Agent` per Reddit's UA guidelines (`platform:app:version (by /u/username)`)
- Use Reddit's official OAuth API (`oauth.reddit.com`) instead of the public `.json` endpoint — requires a registered app + client ID/secret
- Drop Reddit and lean on HN + RSS + arXiv instead

---

## 2. Verified candidates to add (tested just now, real HTTP status)

### RSS — confirmed working, not yet wired in

| Source | URL | Notes |
|---|---|---|
| arXiv cs.LG (Machine Learning) | `http://export.arxiv.org/rss/cs.LG` | 301 → 200 on redirect follow. `aiohttp` follows redirects by default, so this works as-is in `_fetch_rss`. High volume — new papers daily, may need `[:5]` trim or a same-day filter. |
| arXiv cs.CL (Computation & Language / NLP) | `http://export.arxiv.org/rss/cs.CL` | Same as above. Good fit for RAG/eval-related papers. |
| Microsoft Research Blog | `https://www.microsoft.com/en-us/research/feed/` | 200 direct. |
| DeepMind Blog | `https://deepmind.google/blog/rss.xml` | 200 direct. |
| Berkeley AI Research (BAIR) Blog | `https://bair.berkeley.edu/blog/feed.xml` | 200 direct. Academic, technical, good "mechanism" density for Kabir's voice. |
| Simon Willison's Blog | `https://simonwillison.net/atom/everything/` | 200 direct. Atom, not RSS 2.0 — `feedparser` handles both fine. Practitioner voice, LLM tooling/evals focus — strong topical match. |
| AWS Machine Learning Blog | `https://aws.amazon.com/blogs/machine-learning/feed/` | 200 direct. Heavier on product announcements — will need the same "routine announcement" rejection the judge already applies. |
| NVIDIA Blog | `https://blogs.nvidia.com/feed/` | 200 direct. Mixed content (not just AI) — may need a title/keyword pre-filter before it's worth adding. |
| MIT Technology Review | `https://www.technologyreview.com/feed/` | 200 direct. General tech, not ML-specific — would need filtering, lower priority. |
| Stability AI News | `https://stability.ai/news?format=rss` | 301 → 200 on redirect follow. |
| Meta AI Blog | `https://ai.facebook.com/blog/rss/` | 301 → then 404. Dead end, do not use. |

### Confirmed dead — do not use

| Source | URL tried | Result |
|---|---|---|
| Meta AI Blog (both variants) | `ai.meta.com/blog/rss/`, `ai.facebook.com/blog/rss/` | 404 / 301→404 |
| Mistral AI News | `mistral.ai/news/rss.xml`, `mistral.ai/feed.xml` | 404 both |
| DeepLearning.AI — The Batch | `deeplearning.ai/the-batch/feed/` | 404 (redirects to homepage, which itself 308s — no real feed found at this path) |
| Hugging Face Papers RSS | `huggingface.co/papers/rss` | 401 — requires auth, not usable as a public feed |

### Other source types worth considering (not tested — need real design work, not just a URL)

- **GitHub Trending (ML/AI)** — no official RSS, would need a small scraper or a third-party feed proxy. Skip unless you want to build that.
- **Papers with Code** — has an API but requires more integration work than a drop-in RSS feed.
- **Twitter/X** — no free API access anymore, skip.
- **YouTube channel RSS** (e.g. two-minute-papers, Yannic Kilcher) — YouTube does expose per-channel RSS at `https://www.youtube.com/feeds/videos.xml?channel_id=<ID>`, untested here but a known-working pattern. Video-source topics only — fine as a citation source per persona spec section 4.1 ("if a discovered topic naturally suggests video content... that's fine to reference and cite"), just don't generate video for it.

---

## 3. Suggested next step (not yet implemented — waiting on your go-ahead)

If you want more source diversity without touching Reddit's auth problem:

```python
RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss",
    "https://blog.google/technology/ai/rss",
    "https://huggingface.co/blog/feed.xml",
    "http://export.arxiv.org/rss/cs.LG",
    "http://export.arxiv.org/rss/cs.CL",
    "https://bair.berkeley.edu/blog/feed.xml",
    "https://simonwillison.net/atom/everything/",
    "https://deepmind.google/blog/rss.xml",
]
```

This roughly doubles source diversity and adds real academic + independent-practitioner
voices (arXiv, BAIR, Simon Willison) that fit Kabir's "mechanism over hype" bar
better than most lab PR feeds. Didn't apply this yet since you said to hold off
on pipeline changes — this file is just the research so it's ready when you are.
