"""
Dry-run harness for the new media pipeline: runs the REAL node functions
(discover -> filter -> judge -> decide_format -> write_script ->
plan_media_assets) and STOPS before generate_assets, generate_tts, or
assemble_video — i.e. stops before any paid API call (Flora image gen,
ElevenLabs TTS, Flora video gen).

Captures every stage's input/output into DRY_RUN_REPORT.md.
"""
import asyncio
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

REPORT_SECTIONS: list[str] = []


def log_section(title: str, content: str) -> None:
    REPORT_SECTIONS.append(f"## {title}\n\n{content}\n")
    print(f"\n=== {title} ===", flush=True)
    print(content[:2000], flush=True)


def dump(obj) -> str:
    try:
        return "```json\n" + json.dumps(obj, indent=2, default=str) + "\n```"
    except Exception:
        return "```\n" + str(obj) + "\n```"


BASE_STATE = {
    "agent_id": "dry-run",
    "tick_id": "dry-run-tick",
    "persona": {
        "name": "Ada Shen",
        "domain": "ML infrastructure",
        "voice_rules": "terse, technically skeptical, avoids hype",
        "recurring_opinions": ["skeptical of benchmark-only claims", "pro open-weights"],
        "stable_interests": ["inference efficiency", "model serving", "open source tooling"],
        "pushback": ["hype-only announcements", "closed-source-only research"],
    },
    "persona_doc": {},
    "memory_context": [],
    "candidates": [],
    "rejected_topics": [],
    "selected_topic": None,
    "content_type": "text_post",
    "script": None,
    "media_plan": [],
    "image_assets": [],
    "video_asset": None,
    "tts_segments": [],
    "omni_prompt": None,
    "post_text": None,
    "rationale": None,
    "error": None,
}


async def main():
    REPORT_SECTIONS.append(f"# Media Pipeline Dry Run\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n")
    REPORT_SECTIONS.append(
        "Scope: runs discover_topics -> filter_seen -> editorial_judge -> "
        "decide_format -> write_script -> plan_media_assets using the REAL "
        "node code. Deliberately STOPS before generate_assets (Flora image "
        "gen $), generate_tts (ElevenLabs $), and assemble_video (Flora "
        "video gen $) — no paid generation API is called in this run.\n"
    )

    state = dict(BASE_STATE)

    # --- Step 1: discover_topics ---
    from agent.nodes.discover import discover_topics
    state = await asyncio.wait_for(discover_topics(state), timeout=30)
    log_section(
        "Step 1 — discover_topics",
        f"Input: persona={state['persona']['name']} ({state['persona']['domain']})\n\n"
        f"Output: {len(state['candidates'])} candidates found\n\n"
        + dump(state["candidates"][:10]) + ("\n\n(showing first 10 of %d)" % len(state["candidates"]) if len(state["candidates"]) > 10 else "")
    )

    # --- Step 2: filter_seen ---
    from agent.nodes.filter import filter_seen
    from mcp_client import init_mcp_client
    await init_mcp_client()
    candidates_before = len(state["candidates"])
    state = await asyncio.wait_for(filter_seen(state), timeout=60)
    log_section(
        "Step 2 — filter_seen",
        f"Input: {candidates_before} candidates\n\n"
        f"Output: {len(state['candidates'])} candidates passed filter "
        f"(Breeth search_graph dedup — see HOW_IT_ACTUALLY_WORKS.md for known issues)\n"
    )

    # --- Step 3: editorial_judge ---
    from agent.nodes.judge import editorial_judge
    state = await asyncio.wait_for(editorial_judge(state), timeout=60)
    selected = state.get("selected_topic") or {}
    log_section(
        "Step 3 — editorial_judge",
        f"Input: {len(state['candidates'])} candidates\n\n"
        f"Output — selected_topic:\n{dump(selected)}\n\n"
        f"Rejected count: {len(state.get('rejected_topics', []))}\n\n"
        f"Sample rejected (first 3):\n{dump(state.get('rejected_topics', [])[:3])}"
    )

    # --- Step 4: decide_format ---
    from agent.nodes.format import decide_format
    state = decide_format(state)
    detected_format = state["content_type"]
    log_section(
        "Step 4 — decide_format",
        f"Input title: {selected.get('title', '')}\n\n"
        f"Detected content_type (deterministic router): {detected_format}\n\n"
        f"NOTE: forcing content_type='video_post' below to exercise the full "
        f"media pipeline regardless of what the router picked, since the "
        f"user wants to see the whole media planning chain run."
    )
    state["content_type"] = "video_post"

    # --- Step 5: write_script ---
    from agent.nodes.script import write_script
    state = await asyncio.wait_for(write_script(state), timeout=60)
    log_section(
        "Step 5 — write_script",
        f"Input: content_type=video_post, topic={selected.get('title', '')}\n\n"
        f"Output — script:\n{dump(state.get('script'))}"
    )

    # --- Step 6: plan_media_assets ---
    from agent.nodes.plan_assets import plan_media_assets
    state = await asyncio.wait_for(plan_media_assets(state), timeout=60)
    log_section(
        "Step 6 — plan_media_assets",
        f"Input: {len(state['script'].get('beats', []))} script beats\n\n"
        f"Output — media_plan ({len(state['media_plan'])} planned assets):\n"
        + dump(state["media_plan"])
    )

    # --- STOP HERE — next real nodes would be generate_assets (Flora $),
    # generate_tts (ElevenLabs $), assemble_video (Flora $) ---
    log_section(
        "STOPPED — before paid generation calls",
        "The following nodes were NOT executed in this dry run because they "
        "call paid external APIs:\n\n"
        "- `generate_assets` — Flora REST /generate (Nano Banana 2 image gen, "
        "~$0.07-0.11 per asset based on tonight's real runs)\n"
        "- `generate_tts` — ElevenLabs /text-to-speech (per-beat narration audio)\n"
        "- `build_omni_prompt` — free (no API call), but not run since it "
        "depends on validated output from the two paid steps above\n"
        "- `assemble_video` — Flora REST /generate (Gemini-Omni-Flash video "
        "gen, ~144 credits per run)\n\n"
        f"To preview what generate_assets WOULD send, here is the exact "
        f"layered prompt it would build for each planned asset "
        f"(build_asset_prompt is a pure function — calling it does not hit "
        f"any API):\n"
    )

    from agent.nodes.assets import build_asset_prompt
    preview_prompts = [
        {"asset_id": a["asset_id"], "would_send_prompt": build_asset_prompt(a)}
        for a in state["media_plan"]
    ]
    REPORT_SECTIONS.append(dump(preview_prompts))

    # --- Preview: TTS narration chunks (pure function, no ElevenLabs call) ---
    from agent.nodes.generate_tts import build_narration_chunks, _estimate_duration
    narration_chunks = build_narration_chunks(state["script"], len(state["media_plan"]))
    tts_preview = [
        {
            "scene_id": asset["scene_id"],
            "would_send_text_to_elevenlabs": chunk,
            "estimated_duration_seconds": _estimate_duration(chunk),
        }
        for asset, chunk in zip(state["media_plan"], narration_chunks)
    ]
    log_section(
        "Preview — generate_tts (narration chunks, NOT sent to ElevenLabs)",
        "This is the exact text `generate_tts` would send to ElevenLabs "
        "per beat, computed by the real `build_narration_chunks()` pure "
        "function — no synthesis API call made. Voice ID configured: "
        f"{__import__('os').environ.get('ELEVENLABS_VOICE_ID', '(not set)')}\n\n"
        + dump(tts_preview)
    )

    # --- Preview: Omni video prompt (structured 9-section brief) ---
    # build_omni_prompt requires approved (not just planned) assets and real
    # tts_segments with real audio_url values. Since neither exists without
    # paid calls, we construct a CLEARLY LABELED simulated state: same
    # media_plan entries marked "approved" with placeholder output_url
    # strings (not real Flora URLs), and tts_segments using the real
    # narration text + estimated duration from above (not real audio_url).
    # This shows the exact prompt STRUCTURE and CONTENT the real pipeline
    # would produce once assets are actually approved — it does not fabricate
    # any topic/script/narration content, only stands in for not-yet-existing
    # media URLs.
    from agent.nodes.omni_prompt import build_omni_prompt

    simulated_media_plan = [
        {**a, "status": "approved", "output_url": f"<PLACEHOLDER_NOT_REAL_would_be_flora_image_url_for_{a['asset_id']}>"}
        for a in state["media_plan"]
    ]
    simulated_tts_segments = [
        {
            "scene_id": asset["scene_id"],
            "audio_url": f"<PLACEHOLDER_NOT_REAL_would_be_flora_audio_url_for_{asset['scene_id']}>",
            "duration_seconds": preview["estimated_duration_seconds"],
            "text": preview["would_send_text_to_elevenlabs"],
        }
        for asset, preview in zip(state["media_plan"], tts_preview)
    ]

    simulated_state = {
        **state,
        "media_plan": simulated_media_plan,
        "tts_segments": simulated_tts_segments,
    }
    simulated_state = build_omni_prompt(simulated_state)

    log_section(
        "Preview — build_omni_prompt (structured Omni video prompt)",
        "IMPORTANT: this prompt was built by the REAL `build_omni_prompt()` "
        "function using the REAL topic/script/narration content from this "
        "run. The only fabricated parts are the asset/audio URL strings "
        "(clearly marked `<PLACEHOLDER_NOT_REAL_...>`) standing in for URLs "
        "that don't exist yet since no paid image/TTS calls were made. "
        "Every other field — video intent, scene actions, narration text, "
        "style constraints — is exactly what the real pipeline would send "
        "to Gemini-Omni-Flash once real asset/audio URLs are substituted in.\n\n"
        "```\n" + (simulated_state.get("omni_prompt") or "(prompt build failed)") + "\n```"
    )

    # Write the report
    report_text = "\n".join(REPORT_SECTIONS)
    with open("DRY_RUN_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n\n=== DRY RUN COMPLETE — see DRY_RUN_REPORT.md ===", flush=True)


asyncio.run(main())
