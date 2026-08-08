# How ABTalks actually works — honest breakdown

This doc maps every judging criterion to the actual code, tells you the truth
about what's real vs. what's superficial, and points to the exact file/prompt
you'd edit to change behavior.

---

## 1. Sources for news (topic discovery)

**File:** `agent/nodes/discover.py`

Three hardcoded sources, fetched in parallel every tick:

| Source | What | Hardcoded list |
|---|---|---|
| RSS | 4 feeds | OpenAI news, Anthropic news, Google AI blog, HuggingFace blog |
| HN Algolia | Search API, no auth | Query terms: `LLM`, `large language model`, `AI agent`, `open weights`, `inference` (only first 3 used) |
| Reddit | `.json` endpoint, no auth | `r/MachineLearning`, `r/LocalLLaMA` hot posts |

Honest take: this is a thin, generic tech-news scraper. It is **not** scoped to
the persona at all at this stage — it pulls the same 4 RSS feeds + same 2
subreddits + same 5 HN terms regardless of who the persona is. A "ML
infrastructure" persona and a "AI ethics" persona get identical raw candidates.
Persona-fit only happens later, in the judge step. If you want source
diversity per persona, this file is where you'd add per-domain RSS lists.

Dedup at this stage is purely mechanical — SHA1 hash of the URL, first 16
chars. Two articles about the same event from two different URLs are **not**
detected as duplicates here (that's supposed to be Breeth's job downstream).

**To modify:** edit `RSS_FEEDS`, `HN_QUERY_TERMS`, `REDDIT_SUBREDDITS` constants
directly in `agent/nodes/discover.py`.

---

## 2. "Remembering" previously posted content / dedup against history

**File:** `agent/nodes/filter.py` (dedup) + `agent/scheduler.py` (`_fetch_memory_context`)

Claimed mechanism: call Breeth's `search_graph` tool per candidate title,
compare top hit similarity score against a threshold (`0.82`), drop candidates
above it.

**What's actually happening right now:** every single call to `search_graph`
is failing (`filter_seen: search_graph error for '...' — passing through`,
visible in every test run you've done). The `except Exception` block in
`_check_one()` (filter.py) catches the error and returns `keep=True`
unconditionally. So **the dedup filter is currently a no-op** — every
candidate passes through regardless of whether it was covered before.

This means: right now, nothing stops the agent from picking the same topic
twice in a row. The "memory" system exists in code but is not functioning
against your current Breeth account/connection. You need to debug why
`search_graph` throws (likely an auth scope or payload shape issue — worth
checking with `check_tools.py`'s printed input schema, which currently shows
"(schema unavailable)" for every tool, meaning we don't even know the expected
call shape).

Separately, `agent/scheduler.py::_fetch_memory_context()` also calls
`search_graph` (query: `"published post about AI technology"`) to pull recent
posts for **continuity/tone**, not just dedup. This also silently degrades to
`recent_posts = []` on failure — same underlying issue.

**Where this feeds in:** `recent_posts` gets passed into `editorial_judge`'s
system prompt (see section 3) as "don't repeat these angles" context, and into
`PERSONA_SYSTEM_PROMPT`'s `{recent_posts}` slot for tone continuity.

**To fix:** debug the actual `search_graph` call shape against the Breeth MCP
server (their input schema, not ours). Until fixed, treat "remembers previous
content" as **not currently functional**, only architecturally present.

**To modify the threshold/logic:** `SIMILARITY_THRESHOLD = 0.82` in
`agent/nodes/filter.py`.

---

## 3. Topic qualification / editorial judgment (is it worth publishing)

**File:** `agent/nodes/judge.py`

This is a single LLM call (`editorial_judge`) that:
1. Gets all filtered candidates + the persona doc + last 5 recent posts.
2. Scores every candidate 0-10 on four criteria: `relevance`, `novelty`,
   `opinionability`, `timeliness`.
3. Asks the LLM to return a JSON array with exactly one `"selected": true`.
4. Picks that one; everything else becomes `rejected_topics` with a
   `judge_reason` string attached.

Honest take: **there is no actual scoring enforcement in code.** The prompt
tells the LLM "a score below 5 on any single criterion should block
selection," but nothing in `judge.py` checks the returned scores
programmatically — it just trusts whichever object has `"selected": true`.
If the LLM disobeys the "below 5 blocks selection" instruction, there is zero
guardrail. This is prompt-only enforcement, not code-enforced.

Also: if the LLM's JSON response fails to parse (happens — LLMs sometimes wrap
JSON in markdown or add commentary), the fallback is `selected_index = 0` —
i.e. **just pick the first candidate in the list**, no scoring at all. That's
a silent quality cliff with no logging distinguishing "LLM picked this" from
"parser gave up and grabbed index 0."

**Rejection logging:** every rejected candidate gets a `judge_reason` (the
LLM's stated reason) attached and passed to `generate_rationale` later — this
part is real and does get persisted downstream (see section 6).

**Prompt file to edit:** the `_SYSTEM` string inside `agent/nodes/judge.py`
itself (not in `prompts/` — this one lives inline in the node file, which is
inconsistent with `persona.py` being separated out).

**Model used:** `MODEL_FAST` from `agent/llm.py`, temperature `0.3`.

---

## 4. Format decision (video / image / text)

**File:** `agent/nodes/format.py`

This is **not an LLM call** — it's regex keyword matching against the topic
title+summary. Two ordered rule buckets:

- Words like `released`, `launches`, `open source`, `v1/v2/v3` → `video_post`
- Words like `paper`, `arxiv`, `benchmark`, `study` → `image_post`
- Everything else → `text_post` (default)

Honest take: this is crude but deliberately so — the README calls it
"deterministic router," and that's accurate. It's fast and auditable, but it
means format choice has nothing to do with what would actually make a good
video vs. an image vs. text — it's purely lexical pattern matching on the
headline. A launch announcement with none of those exact words defaults to
text_post regardless of whether video would suit it better.

**To modify:** edit the `_RULES` list in `agent/nodes/format.py`.

---

## 5. Persona / editorial voice consistency

**Two layers, and they're not the same thing — worth understanding the split:**

### Layer 1 — static persona definition (`api/routes.py` + `InitRequest`)
Set once at `/init` time: `persona_name`, `persona_domain`, `voice_rules`,
`recurring_opinions`, `stable_interests`, `pushback`. Stored as JSON in
`agents.persona_json` column, never changes unless you re-init.

### Layer 2 — the system prompt template
**File:** `agent/prompts/persona.py` → `PERSONA_SYSTEM_PROMPT`

This is the actual voice-consistency mechanism. It's injected into every
content-generation call (`write_script`, `write_post`) via
`build_persona_prompt()` in `agent/nodes/script.py`. It hard-codes rules like:
- No hype adjectives ("game-changing", "revolutionary")
- One opinion per post, not a summary
- Short sentences, no hedging
- Format-specific rules (280 char lead for text, hook <12 words for video, etc.)

Honest take: consistency here is **entirely prompt-engineering, zero
code-enforced constraints.** There is no character-length validation, no
hype-word filter, no post-generation check that rejects output violating the
rules. If the LLM ignores "no hype adjectives," nothing catches it. The system
relies 100% on the LLM following instructions faithfully every single call.
Given you're currently running on Mistral 7B (not Claude — see the model
saga above in this chat), voice consistency quality will visibly degrade
versus what the prompt was probably designed against (Claude Sonnet).

Also worth flagging: `recurring_opinions`, `stable_interests`, `pushback_list`
are injected into the prompt as **raw lists formatted once at request time**
— there's no mechanism enforcing that generated content actually references
or upholds a specific `recurring_opinion`. The LLM is told to "stay
consistent with these unless new evidence warrants updating" but nothing
verifies it did.

**To modify voice rules:** `agent/prompts/persona.py`, the `PERSONA_SYSTEM_PROMPT`
string directly.

**To modify per-content-type rules** (video script JSON shape, image caption
rules, text post character limits): same file, the "CONTENT FORMAT GUIDANCE"
section, plus the format-specific instruction strings in `agent/nodes/post.py`
(`_IMAGE_INSTRUCTION`, `_VIDEO_INSTRUCTION`, `_TEXT_INSTRUCTION`) and
`agent/nodes/script.py` for video scripts specifically.

---

## 6. Publishing rationale (transparency)

**File:** `agent/nodes/rationale.py`

Another single LLM call, run **after** `write_post`, **before** `persist`.
Takes: selected topic, up to 8 rejected topics with their judge reasons,
content_type. Asks for a JSON object with keys: `why_selected`, `why_now`,
`format_rationale`, `sources`, `rejected_summary`.

This is genuinely stored — `rationale` column on the `Post` table (JSON
string), returned as-is in the `/feed` API response's `rationale` field. This
part is real and does what the README claims: every published post carries a
structured explanation of why it was chosen over the alternatives.

Honest take: it's a second LLM call summarizing the first LLM call's output
(the judge's `judge_reason` strings). If the judge's reasoning was shallow
("high relevance score"), the rationale will just repackage that shallow
reasoning in nicer prose — it doesn't add independent verification or deeper
analysis. It's a formatting/summarization layer, not a second opinion.

If this LLM call's JSON also fails to parse, there's a hardcoded fallback
rationale (`"Selected by editorial judge"`, generic strings) — so even total
LLM failure never blocks publishing; it just produces a low-information
rationale.

**To modify:** `agent/nodes/rationale.py`, the `_SYSTEM`/`_HUMAN` prompt strings.

---

## 7. How content is stored in the DB

**File:** `db/models.py`

Three tables, SQLite by default (`sqlite:///./abtalks.db`), swappable to
Postgres via `DATABASE_URL`.

- **`agents`** — one row per persona. `persona_json` is the full init payload
  serialized as a JSON blob (not normalized into columns — deliberate
  simplicity tradeoff).
- **`posts`** — one row per published post. Has `text`, `media_url`,
  `media_type`, `content_type`, `topic_title/url/source`, `rationale` (JSON
  string), `sources` (JSON array string).
- **`tick_log`** — one row **per scheduler tick**, whether or not it
  published. `published: bool`, `error_msg` if it failed. This is the audit
  trail for "the agent ran but decided not to post" cases (e.g. judge found
  zero candidates).

Honest take: this is a reasonable minimal schema. The one actual bug you hit
today (`DetachedInstanceError`) was because the original `/feed` route built
Pydantic response objects **after** the `with get_session()` block closed —
SQLAlchemy had already detached the ORM objects from their session, so lazy
attribute access failed. Fixed by moving `PostOut` construction inside the
`with` block. Worth knowing this pattern (build DTOs inside the session,
never after) if you touch any other DB-reading route.

---

## 8. Autonomous operation / scheduling

**File:** `agent/scheduler.py`

APScheduler, one job per agent, interval trigger with jitter (`random.randint(150, 240)`
minutes between ticks — 2.5 to 4 hours). First tick fires 5 seconds after
`/init` so you don't wait hours to see if it works.

Each tick: pulls fresh Breeth context (`get_unified_profile` + `search_graph`,
both currently failing silently per section 2), then runs the LangGraph
pipeline (`run_agent_tick` in `graph.py`).

Honest take: the scheduling itself is solid and does what it says — genuinely
autonomous, no per-request generation happens outside this loop
(`/feed` really is read-only, confirmed by reading `routes.py`). The jitter is
real, the failure handling writes a `tick_log` row either way. The weak link
is entirely upstream — the memory context this "autonomous" loop is supposed
to use each cycle isn't currently arriving.

---

## 9. The actual pipeline graph (LangGraph)

**File:** `agent/graph.py`

```
discover_topics → filter_seen → editorial_judge
                                      ├─ (no topic) → END
                                      └─ decide_format
                                              ├─ text_post → write_post
                                              └─ video/image → write_script → generate_assets
                                                                                   ├─ degraded → write_post
                                                                                   ├─ image_post → write_post
                                                                                   └─ video_post → assemble_video → write_post
write_post → generate_rationale → persist → END
```

This part matches the README's degradation chain description accurately —
verified by reading the actual conditional edge functions (`_after_judge`,
`_after_format`, `_after_assets`). No surprises here; this is honestly
implemented as documented.

---

## Where every prompt lives (so you can edit them directly)

| Prompt | File | Used by |
|---|---|---|
| Persona voice/rules (main) | `agent/prompts/persona.py` → `PERSONA_SYSTEM_PROMPT` | `write_script`, `write_post` (via `build_persona_prompt()` in `agent/nodes/script.py`) |
| Editorial judge scoring | `agent/nodes/judge.py` → `_SYSTEM` (inline, not in prompts/) | `editorial_judge` |
| Image caption instructions | `agent/nodes/post.py` → `_IMAGE_INSTRUCTION` | `write_post` |
| Video caption instructions | `agent/nodes/post.py` → `_VIDEO_INSTRUCTION` | `write_post` |
| Text post instructions | `agent/nodes/post.py` → `_TEXT_INSTRUCTION` | `write_post` |
| Rationale generation | `agent/nodes/rationale.py` → `_SYSTEM` / `_HUMAN` | `generate_rationale` |
| Video script writer | `agent/nodes/script.py` (check this file — not fully read above, but this is where the script-writing prompt for video/image beats lives) | `write_script` |

---

## Blunt summary — what's real vs. cosmetic, mapped to the grading criteria

| Grading criterion | Real / working | Cosmetic / broken right now |
|---|---|---|
| **Autonomous operation** | Scheduler + jitter + tick_log audit trail — genuinely works | Memory context feeding into it is broken (see below), so it runs autonomously but "blind" |
| **Quality of editorial decision-making** | LLM scoring rubric exists, rejection reasons captured | Zero code-level enforcement of the scoring rules ("below 5 blocks selection" is prompt-only); JSON-parse failure silently picks index 0 with no scoring at all |
| **Consistency of AI persona** | Detailed, well-written voice prompt (`persona.py`) | 100% prompt-reliance, no character limits/hype-word filters enforced in code; currently running on Mistral-7B, not the (likely intended) Claude model, which will visibly hurt voice fidelity |
| **Effective use of memory** | Architecture is there — dedup filter + recent-posts continuity context, both correctly wired into the judge and persona prompts | **Currently non-functional** — every `search_graph` call is erroring out; the system silently degrades to "no memory" every single tick. This is the biggest gap between what's designed and what's happening. |
| **Transparency of publishing rationale** | Real, stored, returned in `/feed` API, includes rejected-topic reasoning | Rationale quality is only as good as the judge's own (unenforced) reasoning — it's a second LLM restating the first LLM, not independent verification |
| **Overall coherence of feed** | Format router is deterministic/auditable, DB schema is clean | Topic sourcing is generic and not persona-scoped at the discovery stage; persona-fit only kicks in at judge time, after the candidate pool is already generic |

**The single highest-leverage fix, if you want the grading criteria to
actually reflect well:** get `search_graph` working against Breeth. Right
now "effective use of memory" is the weakest link because it's silently
broken, not just weak — that's worse than absent, because the logs claim
graceful degradation ("passing through") but a grader reading the code
without running it would assume memory works.
