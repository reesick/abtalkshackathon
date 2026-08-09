# Issues Found — Root Cause + Fix Plan

You're right on every point. This documents exactly what's broken, why, and how I'm fixing each one. Nothing here is guessed — every root cause below was confirmed by reading the actual code and/or querying the actual database.

---

## 1. Repeated topic ("Responding to the next frontier...") — same post 6 times

**Root cause, confirmed by querying `abtalks.db` directly:**

```
id=1 through id=6, ALL have topic_url = https://openai.com/index/responding-next-frontier-critical-cyber-capabilities
```

This is not "the judge keeps preferring OpenAI." It is a complete failure of requirement #4 from the brief (`1.md`): *"The agent should remember previously published content to maintain continuity and avoid unnecessary repetition."*

The actual mechanism: `agent/nodes/filter.py`'s `filter_seen` node is supposed to drop already-covered topics by calling Breeth's `search_graph` tool. That call has been failing on every single invocation this entire session (visible in every terminal log: `filter_seen: search_graph error for '...' — passing through`). The code's error handling is:

```python
except Exception as exc:
    logger.warning(...)
    return candidate, True  # pass through on any error
```

So when Breeth errors (which is always), every candidate is kept, dedup never happens, and the editorial judge sees the exact same top RSS story every tick and picks it every time because nothing tells it "you already covered this."

I flagged Breeth's `search_graph` as broken in earlier summaries but treated it as an acceptable known-limitation instead of fixing it. That was wrong — this is a graded, required capability, not a nice-to-have.

**Fix:** Add a real, local dedup check that doesn't depend on Breeth at all. Before the judge ever sees a candidate, query the last N `topic_url` / `topic_title` values from our own `posts` table (SQLite, already reliable, already working) and drop exact/near matches. Keep the Breeth `search_graph` call as a secondary signal if it ever starts working, but the primary dedup must be local and not depend on a third-party service that's confirmed non-functional. This directly fixes the "only OpenAI" symptom too — once the same story can't be picked twice, the judge is forced to actually evaluate the rest of the discovered pool (GitHub, HN, arXiv, TechCrunch, etc., all of which are confirmed live and returning real candidates — see `test_discovery_sources.py` results from earlier this session, 14-15 sources passing).

---

## 2. Posts don't follow the writing copy/hook structure you gave me

**Root cause, confirmed by comparing a real live post against `ml_engineer_persona.md` line by line:**

Real output (post id=6, English variant):
> "OpenAI shares its cybersecurity evaluations for Astra, but what about the next frontier of critical capabilities?
>
> OpenAI, the AI powerhouse, recently published a blog post... 1. AI security is no longer... 2. Proactive measures... 3. Staying informed...
>
> What steps are you taking to prepare for the next frontier of critical cyber capabilities in AI?"

Checked against the spec, every one of these is a direct, confirmed violation:

| Spec requirement | What actually happened |
|---|---|
| Hook must be a flat statement, never a question | Hook ends in "?" |
| 2-4 paragraphs of a specific, first-person anecdote | Zero anecdote. Third-person summary of a press release. |
| "The Turn" — one named concept/analogy/sourced stat | Missing entirely |
| No triplet/listicle filler | Post is literally a "1. 2. 3." numbered list |
| Contrast line ("X was never the problem, Y was") | Missing entirely |
| Closer must never be generic engagement-bait ("what do you think") | Closes with "What steps are you taking...?" — exactly the banned pattern |
| First-person voice, "I," a real story that happened to the persona | Entirely third-person "OpenAI announced..." |

This is not a partial miss — the model is essentially ignoring the REQUIRED STRUCTURE section of the system prompt and defaulting to generic press-release-summary mode. I under-reported this earlier in the session as "the deeper voice mechanics aren't always hit" when the reality, looking at this specific output, is closer to "the structure isn't being followed at all this time." That's a meaningfully worse problem than what I told you, and I should have caught it by actually reading a full real output against the spec instead of spot-checking fragments.

**Fix, two parts:**

1. **Code-level structural enforcement**, not just prompt instructions (same philosophy as the em-dash/label sanitizer that already works reliably): detect and reject/regenerate a draft if it (a) ends the first line in "?", (b) contains a numbered list (`^\d+\.\s`), (c) has no first-person pronoun ("I ", "I've", "I'm", "my ") in the first 200 characters, or (d) closes with a generic question pattern. If a draft fails these checks, retry once with a sharper corrective instruction citing exactly what it did wrong; if it fails twice, that is surfaced honestly (logged, and optionally the post is held back) rather than published broken.
2. **Stronger few-shot grounding**: inject the exact 3 worked examples from `ml_engineer_persona.md` section 3.3 directly into the system prompt as few-shot examples (currently they exist only in the spec doc, never actually passed to the model at generation time). Right now the model has never actually seen what a correct post looks like — it's working from abstract structural rules only, which is a much weaker signal than concrete examples.

---

## 3. Sources are "doubled" / only shown as domain, and clicking doesn't work

**Root cause, confirmed by reading `feed.html`'s `sourceLinks()` function and the real API payload:**

Every post's `rationale.sources` array duplicates the same URL as the raw `topic_url` used to build the `topic-block` header. So the UI renders the same link twice: once as the bold title's source line, once again in the "Sources:" footer at the bottom of the post. That's not a bug in link-clickability — those links **are** real `<a href>` tags and are clickable — but showing the identical link twice, with only the domain name visible and no visual distinction from the headline's own source line, reads as broken and redundant. Confirmed: `sourceLinks()` renders `new URL(s).hostname` only, same domain as the topic-block source, directly under it.

**Fix:** Remove the redundant bottom "Sources:" block when it only duplicates the topic's own source URL (the common case for now, since almost every post currently has exactly one source). Keep the bottom sources block only for the case where `rationale.sources` contains additional URLs beyond the primary topic URL (e.g. once a real "rejected alternatives" cross-reference or multi-source story exists). Also make the topic-block source line visually unmistakable as a link (underline on hover, explicit color already correct) so it doesn't read as plain text.

---

## 4. "Remove that text div in the posts"

I need one clarification here rather than guess: do you mean —
(a) the **duplicate "Sources:" div** at the bottom (covered by fix #3 above, and my best guess at what you mean), or
(b) the **entire raw post-text block** should be replaced by something else (a card layout, a shorter preview + "read more", etc.)?

I'm treating this as (a) for now since it's the most concretely broken/duplicated thing I found, but tell me if you meant something else and I'll redo it.

---

## 5. No memes showing

**Root cause, confirmed by checking `.env` and Imgflip's actual API docs live:** `IMGFLIP_USERNAME`/`IMGFLIP_PASSWORD` are not set. Imgflip's `/caption_image` endpoint (the only rendering endpoint, free tier included) genuinely requires a real Imgflip account username/password — there is no anonymous/keyless render path. I confirmed this against Imgflip's own current API documentation, not from memory.

This is not something I can fix without those credentials. **This is still blocking** — I'm not going to fake a meme or skip mentioning it again.

**What I can do in parallel, without credentials:** fix the meme_opportunity detector's over-caution. Separately from the credentials gap, I should check whether the opportunity detector is even trying to greenlight memes at a reasonable rate given the current (broken, repetitive) topic pool — once fix #1 (real topic diversity) lands, more genuinely meme-worthy topics should surface, which matters regardless of credentials.

---

## Fix order (once you confirm this plan)

1. Local DB-based dedup in `filter_seen` — fixes repetition and, as a direct consequence, the "only OpenAI" symptom (highest priority, directly violates a graded requirement)
2. Few-shot examples + code-level structural gate in `write_post` — fixes voice/hook/structure violations
3. Remove duplicate sources block, clarify link styling in `feed.html`
4. Clarify and fix "remove that text div" once you confirm what it refers to
5. Meme rendering — blocked on your Imgflip credentials; I'll wire and fire the moment I have them

I will not touch anything until you say go, and I'll report back after each numbered fix with the real before/after, not a summary claiming it's done.
