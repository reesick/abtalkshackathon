"""
FULL FIRE — runs the entire real media pipeline through the actual node
functions, including PAID calls (Flora image gen, ElevenLabs TTS, Flora
video gen). Downloads every generated asset (images, audio, video) to
local disk and writes a full input/output report to FULL_RUN_REPORT.md.

This is NOT a dry run. Real money is spent when this executes.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import aiohttp

REPORT_SECTIONS: list[str] = []
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "full_run_output")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def log_section(title: str, content: str) -> None:
    REPORT_SECTIONS.append(f"## {title}\n\n{content}\n")
    print(f"\n=== {title} ===", flush=True)
    print(content[:2000], flush=True)


def dump(obj) -> str:
    try:
        return "```json\n" + json.dumps(obj, indent=2, default=str) + "\n```"
    except Exception:
        return "```\n" + str(obj) + "\n```"


async def download_file(session: aiohttp.ClientSession, url: str, local_name: str) -> str:
    """Download a remote asset URL to DOWNLOAD_DIR. Returns the local path."""
    local_path = os.path.join(DOWNLOAD_DIR, local_name)
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


BASE_STATE = {
    "agent_id": "full-run",
    "tick_id": "full-run-tick",
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
    REPORT_SECTIONS.append(f"# Media Pipeline FULL RUN (paid)\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n")
    REPORT_SECTIONS.append(
        "Scope: runs the ENTIRE real pipeline including generate_assets "
        "(Flora image gen $), generate_tts (ElevenLabs $), and assemble_video "
        "(Flora video gen $). All outputs downloaded to `full_run_output/`.\n"
    )

    state = dict(BASE_STATE)

    # --- Step 1: discover_topics ---
    from agent.nodes.discover import discover_topics
    state = await asyncio.wait_for(discover_topics(state), timeout=30)
    log_section("Step 1 — discover_topics", f"{len(state['candidates'])} candidates found")

    # --- Step 2: filter_seen ---
    from agent.nodes.filter import filter_seen
    from mcp_client import init_mcp_client
    await init_mcp_client()
    state = await asyncio.wait_for(filter_seen(state), timeout=60)
    log_section("Step 2 — filter_seen", f"{len(state['candidates'])} candidates after filter")

    # --- Step 3: editorial_judge ---
    from agent.nodes.judge import editorial_judge
    state = await asyncio.wait_for(editorial_judge(state), timeout=60)
    selected = state.get("selected_topic") or {}
    log_section("Step 3 — editorial_judge", f"Selected: {dump(selected)}")

    # --- Step 4: decide_format (forced to video_post) ---
    from agent.nodes.format import decide_format
    state = decide_format(state)
    log_section("Step 4 — decide_format", f"Router picked: {state['content_type']} — forcing video_post")
    state["content_type"] = "video_post"

    # --- Step 5: write_script ---
    from agent.nodes.script import write_script
    state = await asyncio.wait_for(write_script(state), timeout=60)
    narration = state["script"].get("narration", "")
    log_section(
        "Step 5 — write_script",
        f"Script:\n{dump(state['script'])}\n\nNarration word count: {len(narration.split())}"
    )

    # --- Step 6: plan_media_assets ---
    from agent.nodes.plan_assets import plan_media_assets
    state = await asyncio.wait_for(plan_media_assets(state), timeout=60)
    log_section("Step 6 — plan_media_assets", dump(state["media_plan"]))

    # --- Step 7: generate_assets — PAID (Flora image gen) ---
    print("\n\n*** FIRING PAID CALL: generate_assets (Flora image gen) ***\n", flush=True)
    from agent.nodes.assets import generate_assets
    state = await asyncio.wait_for(generate_assets(state), timeout=180)
    log_section(
        "Step 7 — generate_assets (PAID — Flora image gen)",
        dump([{k: v for k, v in a.items() if k != "reference_asset"} for a in state["media_plan"]])
    )

    # --- Step 8: validate_assets ---
    from agent.nodes.validate_assets import validate_assets
    state = await asyncio.wait_for(validate_assets(state), timeout=30)
    approved = [a for a in state["media_plan"] if a["status"] == "approved"]
    log_section(
        "Step 8 — validate_assets",
        f"{len(approved)}/{len(state['media_plan'])} approved\n\n" +
        dump([{k: v for k, v in a.items() if k != "reference_asset"} for a in state["media_plan"]])
    )

    if not approved:
        log_section("ABORTED", "No approved assets — cannot continue to TTS/video. See report above for failure reasons.")
        report_text = "\n".join(REPORT_SECTIONS)
        with open("FULL_RUN_REPORT.md", "w", encoding="utf-8") as f:
            f.write(report_text)
        return

    # Download approved images now
    async with aiohttp.ClientSession() as dl_session:
        for a in approved:
            local_name = f"{a['asset_id']}.png"
            try:
                path = await download_file(dl_session, a["output_url"], local_name)
                print(f"Downloaded image: {path}", flush=True)
            except Exception as exc:
                print(f"Failed to download {a['asset_id']}: {exc}", flush=True)

    # --- Step 9: generate_tts — PAID (ElevenLabs) ---
    print("\n\n*** FIRING PAID CALL: generate_tts (ElevenLabs) ***\n", flush=True)
    from agent.nodes.generate_tts import generate_tts
    state = await asyncio.wait_for(generate_tts(state), timeout=60)
    log_section("Step 9 — generate_tts (PAID — ElevenLabs)", dump(state["tts_segments"]))

    # Download TTS audio
    async with aiohttp.ClientSession() as dl_session:
        for t in state["tts_segments"]:
            local_name = f"tts_{t['scene_id']}.mp3"
            try:
                path = await download_file(dl_session, t["audio_url"], local_name)
                print(f"Downloaded audio: {path}", flush=True)
            except Exception as exc:
                print(f"Failed to download tts {t['scene_id']}: {exc}", flush=True)

    # --- Step 10: build_omni_prompt (free) ---
    from agent.nodes.omni_prompt import build_omni_prompt
    state = build_omni_prompt(state)
    log_section("Step 10 — build_omni_prompt", "```\n" + (state.get("omni_prompt") or "(none)") + "\n```")

    # --- Step 11: assemble_video — PAID (Flora video gen) ---
    print("\n\n*** FIRING PAID CALL: assemble_video (Flora Gemini-Omni-Flash) ***\n", flush=True)
    from agent.nodes.video import assemble_video
    state = await asyncio.wait_for(assemble_video(state), timeout=180)
    log_section("Step 11 — assemble_video (PAID — Flora video gen)", dump(state.get("video_asset")))

    if state.get("video_asset") and state["video_asset"].get("url"):
        async with aiohttp.ClientSession() as dl_session:
            try:
                path = await download_file(dl_session, state["video_asset"]["url"], "final_video.mp4")
                print(f"Downloaded video: {path}", flush=True)
            except Exception as exc:
                print(f"Failed to download final video: {exc}", flush=True)

    # --- Step 12: write_post (caption) ---
    from agent.nodes.post import write_post
    state = await asyncio.wait_for(write_post(state), timeout=60)
    log_section("Step 12 — write_post (caption)", state.get("post_text", ""))

    # --- Step 13: generate_rationale ---
    from agent.nodes.rationale import generate_rationale
    state = await asyncio.wait_for(generate_rationale(state), timeout=60)
    log_section("Step 13 — generate_rationale", dump(state.get("rationale")))

    # Write final report
    report_text = "\n".join(REPORT_SECTIONS)
    with open("FULL_RUN_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n\n=== FULL RUN COMPLETE ===", flush=True)
    print(f"Report: FULL_RUN_REPORT.md", flush=True)
    print(f"Downloaded assets: {DOWNLOAD_DIR}", flush=True)


asyncio.run(main())
