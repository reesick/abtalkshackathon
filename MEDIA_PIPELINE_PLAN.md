# ABTalks Media Generation Pipeline — Implementation Plan

Status: **PLAN ONLY — nothing in this doc has been built or fired.** This is the
design to review before implementation starts. Based on
`ABTalks_Media_Generation_Pipeline_Specification.docx` + everything validated
tonight against the real Flora REST API (workspace, project, model IDs,
reference-image upload flow, `params.image_urls` field, real generation runs).

---

## 0. What we proved tonight (facts, not assumptions)

These are no longer guesses — they were confirmed with real API calls against
your account:

| Fact | Evidence |
|---|---|
| Flora MCP (OAuth, `execute`/`search_docs`) is wrong for this project | Docs explicitly say use REST API key for server-side automation, not MCP/OAuth. Confirmed via `developer.flora.ai/mcp/authentication`. |
| Real REST base URL | `https://app.flora.ai/api/v1` |
| Your workspace | `ws_qd7bh8s3w4fb9p1qqbgm5mfv7n87xzcm` ("sri matale's workspace") |
| A project already exists for this exact use case | `prj_ns7fz7gns0ccb14ppngn3qkf418b2gq7` — named **"Paper-Cut Collage Reel — Motion Design"** |
| "Nano Banana 2" text-only model ID | `t2i-gemini-3.1-flash-image` |
| "Nano Banana 2" **with reference images** model ID | `is2i-gemini-3.1-flash-image` (`images-to-image` capability — plural, multi-ref) |
| Reference images must be uploaded to Flora first (no local paths, no data URLs) | `POST /assets` → signed GCS upload → `POST /assets/{id}/complete` → returns `status: "ready"` + permanent HTTPS URL |
| Reference image field on `/generate` | **`params.image_urls`** (array of HTTPS URLs) — this is undocumented in the public docs but confirmed working: run `run_m179gn1mz1vmk894mc8fqappnd8c2x85` completed successfully using it |
| Real generation cost (image, Nano Banana 2, 2K, 9:16, 3 refs) | `$0.108` charged (estimated `$0.072`, actual ran higher) |
| Real generation latency | ~24–27 seconds actual (estimated 80s — model runs faster than Flora's estimate) |
| Output URL format | `https://media.flora.ai/node-inputs/{date}/anonymous/{uuid}.png` — long-lived, not permanent (download what you need to keep, per Flora's own docs) |
| Polling pattern that works | `GET /runs/{run_id}` → `status: "completed"` + `outputs[0].url` |

This means the plan below is not theoretical — every API call in it has a
proven-working precedent from tonight's session.

---

## 1. Design principle carried over from the spec

> "Visual generation is not a single prompt."

Concretely: **plan the assets → generate with a locked style reference →
validate → generate narration → build a structured master video prompt from
approved pieces → assemble.** Never let one LLM call improvise the whole
video prompt at the end from scratch.

---

## 2. Extended pipeline (mapped onto real graph nodes)

```
editorial_judge
      ↓
decide_format
      ↓
write_script                    (existing — unchanged trigger point)
      ↓
plan_media_assets      [NEW]    ← structured asset plan, not a raw prompt
      ↓
generate_image_assets  [REWRITE of assets.py]  ← real Flora REST, layered prompts, style reference
      ↓
validate_assets         [NEW]   ← LLM-as-judge pass per asset, retry loop
      ↓
generate_tts             [NEW — see §7 open question]
      ↓
sync_scenes_to_tts       [NEW]  ← maps scenes/assets to TTS segment timing
      ↓
build_omni_prompt        [NEW]  ← structured 9-section master brief
      ↓
assemble_video          [REWRITE of video.py]  ← real Flora REST generate call for video model
      ↓
validate_final_video     [NEW]  ← lightweight pass/fail check
      ↓
write_post → generate_rationale → persist → END
```

Text-post path is untouched — none of this fires unless `content_type` is
`image_post` or `video_post`.

---

## 3. Style Reference System (new, foundational)

This is the single highest-leverage change and didn't exist in the codebase
at all before tonight.

### 3.1 What "style reference" means concretely

A **fixed set of 1–3 reference images** (your 3 `refiamegs/*.png` files,
already uploaded and `status: ready` at these permanent URLs from tonight):

```
https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/95bb8a35-00c3-4f0d-b24f-97e259bf5a3c.png
https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/685dc085-d194-49fa-b3e8-476275eb30b4.png
https://media.flora.ai/api-uploads/2026/8/8/user_3EadOsAEAmxHxI72qlQBunOv4jv/48dfc48e-33aa-4b65-a0ab-2dfa9cf317d1.png
```

These get passed as `params.image_urls` on **every single asset generation
call** for this persona/style. Per the spec: "treat the reference as a
consistency constraint, not loose inspiration."

### 3.2 Where this lives in config

New file: `agent/style_reference.py`

```python
STYLE_REFERENCE_IMAGES = [
    "https://media.flora.ai/api-uploads/.../95bb8a35....png",
    "https://media.flora.ai/api-uploads/.../685dc085....png",
    "https://media.flora.ai/api-uploads/.../48dfc48e....png",
]

STYLE_REFERENCE_NAME = "paper-cut-collage-v1"  # for logging/versioning

STYLE_GRAMMAR = {
    "rendering_method": "Flat paper-cut collage illustration",
    "character_construction": "black-and-white halftone photographic head and hands, flat colored paper body/suit",
    "materials": "torn, rough hand-cut paper edges with visible fiber texture on every shape",
    "depth": "each paper layer casts a hard-edged directional drop shadow onto the layer beneath it — real physical stacked-paper depth",
    "palette": "mustard yellow, slate gray, bone cream, deep-red accent used sparingly",
    "lighting": "flat, evenly lit studio lighting",
    "camera": "locked-off straight-on camera, centered symmetrical composition, medium-square framing",
    "editorial_reference": "Vox/New Yorker editorial collage style",
    "frame": "portrait frame (9:16)",
}
```

Rationale for hardcoding rather than deriving from persona: the spec treats
the reference as a **fixed style contract**, independent of which topic is
being illustrated. Only the *subject/action* changes per generation; the
*grammar* (materials, camera, lighting, palette) stays locked — this is
exactly the drummer/box/piano pattern in the spec's example prompts, where
only the action changes.

If you later want per-persona style references (different personas, different
visual languages), this becomes a dict keyed by persona_id instead of a flat
module. Flagging as a future decision, not building it now — you only have
one persona live today.

### 3.3 Model IDs to use (confirmed real)

| Purpose | Model ID | Notes |
|---|---|---|
| Image w/ style reference (primary) | `is2i-gemini-3.1-flash-image` | "Nano Banana 2", multi-image input, confirmed working tonight |
| Image w/ style reference (cheaper/faster fallback) | `is2i-nano-banana-2-lite-is2i-google-gemini` | Lite variant, only 1K resolution, ~20s vs ~65s estimated |
| Video generation | **needs decision — see §8** | No video model confirmed yet |

---

## 4. `plan_media_assets` node (new)

**File:** `agent/nodes/plan_assets.py`

Purpose: convert `script["beats"]` (already exists from `write_script`) into
a structured asset plan, per the spec's table:

```
scene_id | asset_id | asset_type | script_beat | visual_role |
reference_asset | prompt | continuity_notes | reuse | status
```

### 4.1 New state shape

Add to `AgentState` (in `agent/state.py`):

```python
class MediaAsset(TypedDict):
    asset_id: str              # stable, e.g. "asset_01"
    scene_id: str               # which scene/beat this belongs to
    asset_type: str             # "character_action" | "prop" | "background" | "graphic"
    script_beat: str             # the beat key from script["beats"]
    visual_role: str             # what it contributes to the shot
    prompt: str                  # full layered prompt (see §5)
    reference_asset: list[str]   # style reference URLs used
    continuity_notes: str
    reuse: bool
    status: Literal["planned", "generating", "generated", "validating", "approved", "retry", "rejected"]
    output_url: Optional[str]
    validation_notes: Optional[str]
    retry_count: int

class AgentState(TypedDict):
    ... # existing fields unchanged
    media_plan: list[MediaAsset]      # NEW — replaces implicit beat->image mapping
    tts_result: Optional[dict]         # NEW — see §7
    omni_prompt: Optional[str]         # NEW — the structured master prompt, persisted for debugging
```

### 4.2 Logic

One LLM call, given `script["beats"]` + `selected_topic` + `STYLE_GRAMMAR`,
returns a JSON array of `MediaAsset` plan entries (prompt field is a
placeholder here — actual full prompt gets built in step 5, this stage
decides *what* needs to exist and *why*, per spec §4: "the system should not
immediately ask an image model to 'make visuals'. It should first convert
the script into a structured asset plan.")

This directly answers the spec's 4 questions (§19):
- What exactly needs to be visible? → `visual_role`
- Which approved asset represents it? → `asset_id`
- When does it appear relative to narration? → `scene_id` + later TTS sync
- What should it physically do on screen? → `script_beat` action description

---

## 5. Layered prompt construction (rewrite of prompt logic)

**File:** `agent/nodes/generate_assets.py` (renamed from `assets.py` to match
the pipeline stage name)

Per spec §5's table, every prompt is built by filling this exact layer
structure — not concatenated ad hoc:

```python
def build_asset_prompt(media_asset: MediaAsset, topic: dict) -> str:
    """
    Layers, in the exact order the spec specifies:
    Subject → Action/pose → Composition → Materials → Style → Palette →
    Lighting → Depth/shadows → Camera/framing → Texture/edges →
    Continuity → Negative constraints
    """
    return (
        f"{STYLE_GRAMMAR['rendering_method']}: a figure with a "
        f"{STYLE_GRAMMAR['character_construction']}, "
        f"{media_asset['visual_role']} — {media_asset['script_beat']}. "          # subject + action
        f"{STYLE_GRAMMAR['materials']}. "                                          # materials/texture
        f"{STYLE_GRAMMAR['depth']}. "                                              # depth/shadows
        f"Palette: {STYLE_GRAMMAR['palette']}. "                                   # colour
        f"{STYLE_GRAMMAR['lighting']}, {STYLE_GRAMMAR['camera']}. "               # lighting + camera
        f"{STYLE_GRAMMAR['editorial_reference']}. {STYLE_GRAMMAR['frame']}. "     # style + frame
        f"{media_asset.get('continuity_notes', '')} "                              # continuity
        f"Do not introduce new characters, palette shifts, added text, logos, "   # negative constraints
        f"or photorealistic elements not described above."
    )
```

This is exactly the pattern validated tonight (the cyber-shield prompt) —
same skeleton, subject/action swapped per topic, grammar locked.

---

## 6. `generate_image_assets` — real Flora integration (rewrite)

**File:** `agent/nodes/generate_assets.py`

Replaces the broken MCP-based `assets.py` entirely. Uses the proven REST flow:

```python
FLORA_API_BASE = "https://app.flora.ai/api/v1"
FLORA_MODEL_PRIMARY = "is2i-gemini-3.1-flash-image"     # Nano Banana 2, with refs
FLORA_MODEL_FALLBACK = "is2i-nano-banana-2-lite-is2i-google-gemini"  # cheaper retry

async def _generate_one_asset(session, media_asset: MediaAsset, workspace_id: str, project_id: str) -> MediaAsset:
    payload = {
        "type": "image",
        "prompt": media_asset["prompt"],
        "workspace_id": workspace_id,
        "project_id": project_id,
        "model": FLORA_MODEL_PRIMARY,
        "params": {
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "image_urls": STYLE_REFERENCE_IMAGES,
        },
    }
    resp = await session.post(f"{FLORA_API_BASE}/generate", json=payload, headers=AUTH_HEADER)
    run = resp.json()
    # poll run["poll_url"] every 3s until completed/failed (same pattern validated tonight)
    ...
```

Key differences from tonight's manual test, now made systematic:
- **Concurrency**: fire all planned assets in parallel (`asyncio.gather`),
  not sequentially — spec doesn't forbid this and it's the obvious win over
  tonight's one-at-a-time manual curl calls.
- **Per-asset retry** using `FLORA_MODEL_FALLBACK` if primary model run fails
  (not just timeout — actual `status: "failed"` from Flora), per spec §16
  failure table: "retry only that asset; do not regenerate unrelated approved
  assets."
- **Idempotency-Key header** on retries (per Flora's own idempotency docs) —
  we didn't need this tonight since nothing failed, but production retries
  should carry it to avoid double-billing on network-error retries.
- **Workspace/project ID config**: hardcode the confirmed
  `ws_qd7bh8s3w4fb9p1qqbgm5mfv7n87xzcm` / `prj_ns7fz7gns0ccb14ppngn3qkf418b2gq7`
  as defaults in `.env` (`FLORA_WORKSPACE_ID`, `FLORA_PROJECT_ID`), not
  re-fetched via `/workspaces` + `/projects` every tick — that's wasted
  latency for values that don't change.

### 6.1 Env vars needed (new)

```
FLORA_API_BASE=https://app.flora.ai/api/v1
FLORA_API_KEY=<redacted — see .env, do not commit>     # move out of the malformed line in .env
FLORA_WORKSPACE_ID=ws_qd7bh8s3w4fb9p1qqbgm5mfv7n87xzcm
FLORA_PROJECT_ID=prj_ns7fz7gns0ccb14ppngn3qkf418b2gq7
```

Note: your current `.env` has the Flora key on a malformed line (`flroa api
ak_...` — not `KEY=value` format, so `python-dotenv` never actually loads it).
This plan fixes that as part of implementation, not left broken.

---

## 7. TTS stage — CONFIRMED: ElevenLabs

**Decision locked in.** ElevenLabs API key verified working tonight
(`GET /v1/voices` returned 20 premade voices successfully).

### 7.1 Confirmed facts

| Fact | Value |
|---|---|
| Provider | ElevenLabs |
| API key | `<redacted — see .env, do not commit>` (now in `.env` as `ELEVENLABS_API_KEY`) |
| Base URL | `https://api.elevenlabs.io/v1` |
| Auth header | `xi-api-key: {key}` (not Bearer — ElevenLabs uses its own header) |
| Voices endpoint | `GET /v1/voices` — confirmed returns 20 premade voices |

### 7.2 Voice selection

**User-specified voice ID: `30UAuH7CeDSQhCCijs1Y`** — this overrides the
earlier "River" recommendation. Not one of the 20 premade voices returned by
tonight's `GET /v1/voices` call (that list only showed premade catalog
voices) — this is likely a custom/cloned voice on the account, or a premade
voice from a page beyond what was returned. **Not yet verified to exist or
work** — the TTS node's first real call will confirm it. If this voice ID
returns a 404 or similar, fall back to River (`SAz9YHcvj6GT2YYXdXww`) as the
documented backup.

### 7.3 Model selection

ElevenLabs offers several TTS models (`eleven_multilingual_v2`,
`eleven_turbo_v2_5`, `eleven_flash_v2_5`, etc.) — visible per-voice in the
`verified_languages` field from tonight's response. For narration-quality
English output, `eleven_multilingual_v2` is the standard choice (highest
quality, all voices support it per tonight's response). `eleven_turbo_v2_5`
is the faster/cheaper alternative if latency matters more than fidelity —
not needed here since narration generation isn't the bottleneck (image/video
generation is far slower).

**Chosen: `eleven_multilingual_v2`**

### 7.4 API call shape (not yet fired — for implementation)

```python
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_VOICE_ID = "30UAuH7CeDSQhCCijs1Y"  # user-specified
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

async def generate_tts(narration_text: str, session) -> dict:
    resp = await session.post(
        f"{ELEVENLABS_API_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": narration_text,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
    )
    # Response is raw audio bytes (audio/mpeg), not JSON — needs to be
    # uploaded somewhere (Flora assets, or your own storage) to get a URL
    # the Omni prompt / video stage can reference.
    audio_bytes = await resp.read()
    ...
```

**Open sub-question, not yet resolved:** ElevenLabs returns raw audio bytes
directly (not a hosted URL like Flora does). The spec's `TTS` data model
(§15) expects an `audio_url`. Two options:
1. Upload the returned audio bytes to Flora's asset endpoint (`POST /assets`
   with `source: "signed-url"`, same upload flow validated tonight for
   images) to get a permanent HTTPS URL Flora's video model can reference.
2. Store audio bytes in your own storage (S3, local disk served via FastAPI
   static route) if the video assembly step doesn't require a Flora-hosted
   URL specifically.

**Recommendation: option 1** — reuse the exact asset upload flow already
proven tonight, keeps all media assets (images + audio) in one place (Flora
workspace), and guarantees the eventual video-generation call can reference
it the same way it references reference images. This adds zero new
infrastructure since the upload code path already needs to exist for
images.

### 7.5 Segment-level TTS (for scene sync, per spec §11)

Spec wants TTS "segmented" to map to beats/scenes (`Beat 01 → tts_01`, etc).
ElevenLabs doesn't return per-word/per-sentence timestamps in the basic
`/text-to-speech` endpoint — that requires their separate
`/text-to-speech/{voice_id}/stream/with-timestamps` or the alignment feature.
**Not yet confirmed working** — this is a second, smaller open item: either
call TTS once per scene/beat (simplest — narration text is already split by
beat in `script["beats"]`, so generate one audio clip per beat and concatenate
timing from clip durations) rather than once for the whole narration and
trying to align after the fact. This is simpler and avoids needing the
timestamp-alignment API at all.

**Recommendation: one ElevenLabs call per beat**, not one call for the whole
script. Matches the spec's `Beat 01 → tts_01` mapping exactly, avoids the
alignment API entirely, and each MediaAsset's `scene_id` already ties 1:1 to
a TTS clip with a known duration (from the audio file itself).

---

## 8. Video generation model — CONFIRMED

**Decision locked in.** `GET /models?type=video` returned the real Flora
catalog. Found the Google Omni equivalent:

| Model | Model ID | Capability | Cost | Notes |
|---|---|---|---|---|
| **Gemini-Omni-Flash (chosen)** | `r2v-gengateway-omni-flash-gg` | `frames-to-video` | 144 credits, ~70s | Takes reference images (your approved assets) + prompt → video. This is the correct one — matches spec's "attach image assets + TTS + prompt → Google Omni." |
| Gemini-Omni-Flash (text-only variant) | `t2v-gengateway-gemini-omni-flash-t2v-c` | `text-to-video` | 144 credits, ~70s | No image input — wrong variant for this pipeline, which always has approved frames by the time video generation runs. |
| Gemini-Omni-Flash (video edit variant) | `v2v-gengateway-gemini-omni-flash-v2v-b` | `video-to-video` | 144 credits, ~70s | For editing an existing video, not initial generation — not used here. |

**Important constraint discovered:** `r2v-gengateway-omni-flash-gg` has **no
`duration` parameter** in its param list — unlike most other video models on
Flora (Kling, Seedance, Veo all expose explicit `duration` options like
"5 seconds," "10 seconds," etc). This model's output duration appears to be
fixed or auto-determined, not settable via `params`. Aspect ratio options are
limited to `16:9` and `9:16` only (matches our 9:16 portrait need).

**Open sub-decision:** if hitting an exact target duration (e.g. "10 seconds"
per beat count) matters more than using the literal Gemini-Omni branded
model, a duration-configurable `frames-to-video` alternative exists:
`r2v-kling-o3` (523 credits, explicit 3–15s duration options, same
`frames-to-video` capability). This is a fallback, not the primary choice —
Gemini-Omni-Flash is cheaper (144 vs 523 credits) and is the actual
spec-intended model family. Recommend testing Gemini-Omni-Flash first with
one real dry run to see what duration it actually produces before deciding
whether the fallback is needed.

### 8.1 API call shape (not yet fired — for implementation)

```python
FLORA_VIDEO_MODEL = "r2v-gengateway-omni-flash-gg"

payload = {
    "type": "video",
    "prompt": omni_prompt,  # the structured 9-section brief from §10
    "workspace_id": FLORA_WORKSPACE_ID,
    "project_id": FLORA_PROJECT_ID,
    "model": FLORA_VIDEO_MODEL,
    "params": {
        "aspect_ratio": "9:16",
        "image_urls": [a["output_url"] for a in approved_media_assets],  # frames-to-video input
    },
}
# POST /generate, poll /runs/{run_id} same pattern as image generation
```

Note: the exact field name for passing multiple reference frames to a
`frames-to-video` model was not confirmed by tonight's `/models` call (the
param list only shows `aspect_ratio`; no `image_urls`/`video_urls` field is
listed for this specific model, unlike some other r2v/v2v models in the
catalog that do list `video_urls` explicitly, e.g.
`r2v-seedance-2.0-enhancor`). This needs the same treatment as §6's
`params.image_urls` discovery — likely works the same way (undocumented but
functional) but **must be verified with one real dry-run call**, not assumed,
before wiring into the pipeline permanently.

---

## 9. `validate_assets` node (new)

**File:** `agent/nodes/validate_assets.py`

Per spec §9's checklist, one LLM-as-judge call per generated asset (vision
model, since it needs to look at the actual image):

```
Checks:
- required subject present
- intended action/pose present
- style reference respected (compare against STYLE_GRAMMAR description)
- palette/material treatment consistent
- composition/framing matches prompt
- no accidental text/logos/unrelated objects
```

Needs a vision-capable model call — `get_llm()` currently returns
`ChatBedrock` with a text model. This requires either:
- Passing the image URL to a vision-capable Bedrock model (needs to confirm
  your Bedrock account has vision model access — untested tonight), or
- Using a vision-capable Flora model via a second Flora call, or
- A simpler heuristic-only check (dimensions, file exists, no error) as a
  cheaper first pass, escalating to real vision validation only if you want
  the full spec behavior.

Given tonight's discovery that your Bedrock account has limited model access
(most Claude models rejected, only Mistral worked), **I'd flag vision-model
validation as a likely second blocker** — need to confirm a working vision
model before this stage can do real visual QA rather than just "did the API
call succeed."

On rejection: retry using the *same* reference + a corrected prompt (spec
§16), max N retries, then mark `status: "rejected"` and block final assembly
per spec §9: "Do not send an unapproved asset to the final video-generation
stage."

---

## 10. `build_omni_prompt` node (new)

**File:** `agent/nodes/omni_prompt.py`

Builds the structured 9-section brief from spec §13, populated from
**structured data**, not string concatenation of arbitrary LLM output (spec
§17: "Generate the Omni prompt from structured metadata rather than manually
concatenating arbitrary strings.")

```python
def build_omni_prompt(state: AgentState) -> str:
    sections = []
    sections.append(f"1. VIDEO INTENT\n{_video_intent(state)}")
    sections.append(f"2. REFERENCE ASSETS\n{_asset_inventory(state['media_plan'])}")
    sections.append(f"3. VISUAL STYLE\n{_style_block(STYLE_GRAMMAR)}")
    sections.append(f"4. AUDIO / NARRATION\n{_audio_block(state['tts_result'])}")
    sections.append(f"5. SCENE TIMELINE\n{_scene_timeline(state['media_plan'], state['tts_result'])}")
    sections.append("6. CONTINUITY\nDo not redesign characters, props, palette or materials between shots. Do not introduce new visual styles.")
    sections.append(f"7. CAMERA / MOTION\n{STYLE_GRAMMAR['camera']}. Preserve composition on locked-off scenes.")
    sections.append("8. NEGATIVE CONSTRAINTS\nDo not add unrequested objects, text, logos, photorealistic elements, palette changes, camera movements, or character changes.")
    sections.append(f"9. OUTPUT\nFormat: mp4. Aspect ratio: 9:16. Duration: {_total_duration(state['tts_result'])}s.")
    return "\n\n".join(sections)
```

This prompt gets **persisted** (per spec §17: "Persist prompts alongside
generated assets for reproducibility") — add `omni_prompt` to the `Post`
DB model or a new `MediaJob` table (see §11).

---

## 11. Data model changes (DB)

Per spec §15. Current `db/models.py` has no concept of a media job, scenes,
or per-asset records — only the flat `Post` table with `media_url`/`media_type`.

New table needed: `MediaJob` (or extend `Post` — recommend a new table, since
one `Post` should link to many `MediaAsset` rows and the relationship doesn't
fit cleanly into `Post`'s current flat shape):

```python
class MediaJob(Base):
    __tablename__ = "media_jobs"
    job_id = Column(String, primary_key=True)
    post_id = Column(Integer, nullable=True)       # FK to posts.id once persisted
    script_id = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    style_reference_id = Column(String, nullable=False)  # "paper-cut-collage-v1"
    omni_prompt = Column(Text, nullable=True)
    final_video_url = Column(String, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)

class MediaAssetRow(Base):
    __tablename__ = "media_assets"
    asset_id = Column(String, primary_key=True)
    job_id = Column(String, nullable=False, index=True)
    scene_id = Column(String, nullable=False)
    asset_type = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    reference_asset = Column(Text, nullable=True)   # JSON array of URLs used
    output_url = Column(String, nullable=True)
    status = Column(String, nullable=False)
    validation_notes = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
```

This gives you exactly what spec §15 asks for, and makes the whole pipeline
debuggable after the fact (spec §17: "Keep stable IDs for scenes and assets
so prompts, files and video instructions can reference the same objects.")

---

## 12. Failure/retry logic (per spec §16, mapped to real code)

| Spec failure case | Implementation |
|---|---|
| Asset generation fails | `_generate_one_asset` catches non-200/failed status, retries that one asset with `FLORA_MODEL_FALLBACK`, max 2 retries, `retry_count` tracked on `MediaAsset` |
| Asset violates style (validation rejects it) | Regenerate using same `image_urls` + prompt with an appended correction note from `validation_notes` |
| Missing asset (never generated) | Block `build_omni_prompt` — raise and degrade `content_type` to `image_post` (using whatever assets *did* succeed) or `text_post` if zero assets succeeded, same degradation pattern the current code already has |
| TTS failure | Retry TTS call; script itself is untouched (already approved) |
| Timing mismatch | Recompute `sync_scenes_to_tts` before building Omni prompt — never build the prompt with stale timing |
| Omni generation failure | Retry video stage with identical approved assets/audio; only regenerate the *prompt* if the error message indicates a prompt-content rejection, not a transient failure |
| Final video quality issue | Route back to `validate_assets` or `build_omni_prompt`, not a full pipeline restart |

---

## 13. What I'm explicitly NOT deciding for you

1. **Per-persona vs. global style reference** — building global-only for now
   since you have one persona; flagged as a future extension point.
2. **Vision-model validation** — flagged as likely blocked by the same
   Bedrock model-access limits we hit tonight; may need a heuristic-only
   fallback.
3. **Whether to keep the MCP client/Breeth wiring untouched** — yes, this
   plan only touches the image/video generation nodes, not `filter.py`,
   `persist.py`, or the Breeth memory system, which is a separate known-broken
   issue (see `HOW_IT_ACTUALLY_WORKS.md` §2).

**Resolved tonight:**
- TTS provider: ElevenLabs (§7), key verified working, voice = `30UAuH7CeDSQhCCijs1Y`
  (user-specified, overriding the earlier "River" pick), model =
  `eleven_multilingual_v2`, segment strategy = one call per beat.
- Video model: `r2v-gengateway-omni-flash-gg` (Gemini-Omni-Flash,
  frames-to-video) (§8), confirmed present on this workspace, cost/capability
  known. Exact reference-image field name for this specific model still
  needs one verification call before first real use (not a blocker to
  writing the code, since the same fallback/retry pattern from §12 applies
  if the field name guess is wrong).

---

## 14. Build order (once you confirm §8 — video model discovery)

1. `agent/style_reference.py` — style grammar + reference URLs (no external calls, pure config)
2. `agent/tts_config.py` — ElevenLabs voice/model constants (§7, resolved)
3. `db/models.py` — add `MediaJob` + `MediaAssetRow` tables
4. `agent/state.py` — add `media_plan`, `tts_result`, `omni_prompt` fields
5. `agent/nodes/plan_assets.py` — new node
6. Rename `agent/nodes/assets.py` → `agent/nodes/generate_assets.py`, rewrite to use real Flora REST + layered prompts
7. `agent/nodes/validate_assets.py` — new node (heuristic-first, vision-upgrade later)
8. `agent/nodes/generate_tts.py` — new node, one ElevenLabs call per beat, upload result to Flora assets for a URL
9. `agent/nodes/omni_prompt.py` — new node
10. Rewrite `agent/nodes/video.py` — real Flora REST video call, blocked on §8 discovery
11. `agent/graph.py` — rewire edges to insert the new nodes into the existing conditional routing
12. Test end-to-end with a **single manual dry run** (like tonight, but through the actual pipeline code) before ever letting the scheduler trigger it live

Nothing above has been executed. Waiting on confirmation to run the one
read-only `GET /models?type=video` discovery call for §8 — the last blocker
before implementation can start.
