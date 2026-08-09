# Meme Subsystem Implementation Report

Implements `meme_intelligence_humour_system_implementation.md`, using the
architecture from Kim & Chilton 2025 ("AI Humor Generation: Cognitive,
Social and Creative Skills for Effective Humor",
https://arxiv.org/html/2502.07981v1 — read in full, not skimmed).

## 1. Files changed

**New — `meme/` package**
- `meme/providers/imgflip.py` — Imgflip REST client (get_memes, caption_image, render_with_fallback)
- `meme/templates/registry.py` — persistent template registry (DB-backed)
- `meme/templates/ingestion.py` — sync job (Imgflip -> registry)
- `meme/templates/semantics.py` — semantic enrichment (text-only, see limitations)
- `meme/templates/retrieval.py` — candidate retrieval/pre-filter
- `meme/templates/ranking.py` — template ranking formula + exploration
- `meme/templates/cooldown.py` — template/family/mechanism repetition control
- `meme/humour/observation.py` — Stage 1: Observation
- `meme/humour/ideation.py` — Stage 2: Visual Humour Ideation
- `meme/humour/narrative.py` — Stage 3: Narrative/Conflict Extrapolation
- `meme/humour/caption.py` — Stage 4: Caption Generation
- `meme/humour/ranking.py` — Stage 5: Judge (separate call from generation)
- `meme/humour/safety.py` — AI-ish detector, unsafe-content denylist, length validation
- `meme/humour/skill.py` — orchestrates stages 1-5 for one template
- `meme/memory/usage.py` — per-post usage records (DB-backed)
- `meme/memory/repetition.py` — lexical joke-similarity (no embedding provider exists in this project)
- `meme/memory/performance.py` — rolling performance update (real path, no real engagement data source yet)
- `meme/renderer/render.py` — renderer provider abstraction
- `meme/opportunity.py` — meme opportunity detector (NO MEME as a valid, common outcome)
- `meme/engine.py` — `MemeEngine` top-level orchestrator

**New — graph nodes**
- `agent/nodes/meme_opportunity.py`
- `agent/nodes/meme_generate.py` (combines select+generate+judge — see rationale in the file's docstring)

**New — tests**
- `test_meme_subsystem.py` — 23 unit tests (cooldown, similarity, safety, ranking, registry, opportunity fallback)
- `test_imgflip_smoke.py` — live provider smoke test, no publishing
- `dry_run_meme_pipeline.py` — full end-to-end dry run, real discovery + real Imgflip fetch, no rendering/publishing

**Modified**
- `agent/state.py` — added `MemeOpportunity`, `MemeTemplateCandidate`, `MemeCaptionCandidate`, `MemeJudgeScore`, `MemeResult` TypedDicts; `content_type` is now `Literal["meme_post", "text_post"]`
- `agent/graph.py` — rewired: `discover -> filter -> judge -> meme_opportunity -> [meme_generate -> ] write_post -> generate_rationale -> persist`. Image generation (`write_script`/`plan_media_assets`/`generate_assets`/`validate_assets`/`decide_format`) disconnected — files remain on disk. Video was already disconnected in a prior pass. **TTS (`generate_tts.py`) was explicitly not touched, per instruction** — it remains exactly as it was (disconnected, on disk, not reconnected either).
- `agent/nodes/post.py` — added a Hinglish text-post path (Mixtral-8x7b, confirmed via direct testing to produce more natural Hinglish than Mistral-7b) and a short meme-accompanying-post path for `meme_post`
- `agent/nodes/persist.py` — `_media_url` now reads from `meme_result` instead of `image_assets`; added `record_usage()` call so meme memory actually accumulates across ticks
- `agent/llm.py` — added shared `repair_json()` helper (see bugs found below)
- `db/models.py` — added `MemeTemplate`, `MemeUsage` tables
- `.env.example` — added `IMGFLIP_USERNAME`, `IMGFLIP_PASSWORD`, `MEME_*_COOLDOWN_POSTS`

## 2. Database changes

Two new tables (SQLite dev DB, created via `create_tables()`):
- `meme_templates` — registry with semantic metadata, popularity/freshness, usage counters, cooldown fields
- `meme_usage` — per-post usage record for repetition/performance tracking

Sync never wipes `last_used_at`, `times_used`, `times_posted`, or semantic metadata (verified by the `sync_meme_templates` unit test — a second sync only updates provider-sourced fields).

## 3. Providers integrated

- **Imgflip**: `get_memes` (free, no auth) confirmed live — 100 real templates fetched. `caption_image` (POST-body auth) coded and tested for the *request path*; not exercised end-to-end because `IMGFLIP_USERNAME`/`IMGFLIP_PASSWORD` are not yet configured (per your instruction — "we'll test it later with adding shit in env"). `/automeme`, `/ai_meme`, `/search_memes` intentionally NOT used (spec section 99).

## 4. Template registry status

PASS. 100 real Imgflip templates synced into `meme_templates`. 10 curated templates pre-annotated with real semantic metadata (Drake, This Is Fine, Two Buttons, Distracted Boyfriend, Galaxy Brain, Expanding Brain, Change My Mind, Roll Safe, Is This a Pigeon, Waiting Skeleton) so the system has usable semantics from day one.

## 5. Template semantic enrichment status

PARTIAL, honestly labeled. **No vision-capable model is available on this project's Bedrock account** (confirmed in earlier sessions — only Mistral text models are invocable; AWS credentials for `list_foundation_models` are also currently stale, confirmed by a live API call failing with `UnrecognizedClientException`). `meme/templates/semantics.py` calls a real text-only model using the template NAME as the only signal, and the enrichment prompt explicitly asks the model to self-report low confidence rather than invent plausible visual details. This is weaker than the spec's intended vision-based enrichment and is labeled as such in the code and in this report — not hidden.

## 6. Template ranking status

PASS. Unit-tested (candidates sorted correctly, all scoring fields present) and exercised live in the dry run (real templates ranked by semantic_fit/mechanism_fit/visual_fit/popularity/freshness/historical_performance, repetition-penalized, exploration bonus applied).

## 7. Template repetition status

PASS. Unit-tested against the spec's own worked examples (section 105/106): same-template-within-cooldown penalty, same-family-different-template penalty, same-mechanism-repeated penalty, near-duplicate caption similarity penalty. Overused templates (Drake, Distracted Boyfriend, This Is Fine) get a longer cooldown per spec section 14.

## 8. Humour Skill status

PASS, with one honest architectural gap and one real bug class found and fixed:

- **Observation, Ideation, Narrative Extrapolation, Caption Generation, Judge** are five separate LLM calls (never the same call generating and judging — spec section 92), each independently callable and logged.
- **Gap**: Observation works from template *semantic metadata*, not actual image content (same no-vision-model limitation as enrichment). Labeled in `observation.py`'s docstring and in each observation's `_grounding_disclaimer` field.
- **Bug class found via direct testing, not assumed**: Mistral/Mixtral occasionally emit Python-style `\'` inside JSON string values, which is invalid JSON. Fixed with a shared `repair_json()` helper applied everywhere this project parses structured JSON from a model response (7 call sites in `meme/`, plus `agent/nodes/rationale.py`).
- **Second bug class found via direct testing**: judging/generating large candidate batches (24 at once) in a single call risked truncation (`Unterminated string`) or count mismatches on this model. Fixed by: raising `max_tokens` (2048 -> 4096) on both the judge and caption-generation calls, batching judge calls at 8 candidates at a time, and adding one retry before falling back.
- **Third bug found**: the original fallback-on-judge-failure scored every candidate at `0.0`, which meant ANY judge parse failure would auto-reject even a genuinely good caption (verified this concretely: a real run scored a good caption `8.37` after the fix, where the old code would have forced `0.0`). Fixed with a real heuristic-only fallback (`_heuristic_fallback_score`) using caption length/structure/ai-ish signals instead of zeros.

## 9. Repetition (joke similarity) status

PASS, with an honest scope reduction. Spec section 43 explicitly says: "If the project already has an embedding system, reuse it. Do not introduce a new embedding provider unnecessarily." This project has no embedding provider anywhere (checked `agent/llm.py`, `mcp_client.py`). Rather than add one just for this feature, `meme/memory/repetition.py` uses lexical (Jaccard) token-overlap similarity instead — weaker than true semantic embedding similarity, labeled as such in the module docstring, upgradeable later if an embedding provider is added for other reasons.

## 10. Live dry-run result

Ran three times, real network calls, real LLM calls, no publishing, no rendering:

1. Real discovered topic ("Responding to the next frontier of critical cyber capabilities") correctly rejected by the opportunity detector — NO MEME, with a specific, non-generic reason. This is section 116's required behavior working correctly, not a failure.
2. A clearly-labeled synthetic meme-worthy topic exercised the full pipeline: opportunity -> 100 real templates ranked -> humour skill (5 real LLM stages) -> judge. Produced genuinely funny, on-topic candidates (e.g., a "Batman Slapping Robin"-style caption about an AI coding agent deleting failing tests).
3. After the batching/fallback fixes, a direct `MemeEngine.process()` call produced a final candidate scoring **8.37** (above the 6.5 quality gate), then correctly stopped at rendering with `should_make_meme: False` and a clear reason, because Imgflip credentials are not configured yet — exactly where you asked me to stop.

## 11. Environment variables required

All optional, degrade gracefully if absent (verified — Product Hunt/YouTube/Imgflip all log a clear skip message rather than crashing):

```
IMGFLIP_USERNAME=
IMGFLIP_PASSWORD=
MEME_TEMPLATE_COOLDOWN_POSTS=5
MEME_FAMILY_COOLDOWN_POSTS=2
MEME_MECHANISM_COOLDOWN_POSTS=2
MEME_OVERUSED_TEMPLATE_COOLDOWN_POSTS=8
```

## 12. Known limitations (honest, not hidden)

- No vision model available — observation/enrichment/final-judge all work from text/metadata, not actual images. This is the single biggest gap vs. the paper's architecture.
- No embedding provider — joke similarity uses lexical overlap, will miss conceptually-similar-but-differently-worded jokes.
- No real engagement/performance data source exists yet — `meme/memory/performance.py`'s update path is real code with nowhere to pull real numbers from today.
- Small-model JSON reliability remains an inherent source of occasional per-candidate score loss even with batching+retry+heuristic fallback — mitigated, not eliminated.
- Imgflip rendering is coded and unit-path-tested (free `get_memes` confirmed live) but not exercised end-to-end — waiting on credentials, per instruction.
- `meme_generate.py` combines what the spec's suggested file layout calls three separate node files (select/generate/judge) into one node, because `MemeEngine.process()` already runs them as one interdependent sequence per template candidate — see that file's docstring for the reasoning.

## 13. What was explicitly NOT touched, per instruction

- `agent/nodes/generate_tts.py`, `agent/nodes/omni_prompt.py` — untouched, remain disconnected exactly as before.
- `agent/nodes/video.py` — untouched, was already disconnected before this task.
- Image generation nodes (`script.py`, `plan_assets.py`, `assets.py`, `validate_assets.py`, `format.py`) — disconnected from the graph as instructed, files left on disk, not deleted, not modified.
