"""
STAGE 2 — resumes from _stage1_state.json (images + audio already generated
and downloaded in stage 1). Fires assemble_video (PAID, tries Gemini-Omni-Flash
first, falls back to Seedance 2.0 Reference (Fast) automatically), then
write_post. Downloads the resulting video if generation succeeds. Reports
honestly on success or failure — no rigging.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

REPORT_SECTIONS: list[str] = []
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "full_run_output")
STATE_FILE = os.path.join(os.path.dirname(__file__), "_stage1_state.json")
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
    local_path = os.path.join(DOWNLOAD_DIR, local_name)
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


async def main():
    REPORT_SECTIONS.append(f"# Media Pipeline STAGE 2 (video, paid)\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n")

    if not os.path.exists(STATE_FILE):
        print(f"ERROR: {STATE_FILE} not found. Run full_run_stage1_assets.py first.", flush=True)
        return

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    approved = [a for a in state.get("media_plan", []) if a["status"] == "approved"]
    log_section(
        "Resumed state from Stage 1",
        f"Topic: {state.get('selected_topic', {}).get('title')}\n"
        f"Approved image assets: {len(approved)}\n"
        f"TTS segments: {len(state.get('tts_segments', []))}\n"
        f"Omni prompt present: {bool(state.get('omni_prompt'))}"
    )

    print("\n\n*** FIRING PAID CALL: assemble_video (Flora video gen) ***\n", flush=True)
    from agent.nodes.video import assemble_video, FLORA_VIDEO_MODEL_PRIMARY, FLORA_VIDEO_MODEL_FALLBACK
    log_section("Models configured", f"Primary: {FLORA_VIDEO_MODEL_PRIMARY}\nFallback: {FLORA_VIDEO_MODEL_FALLBACK}")

    state = await asyncio.wait_for(assemble_video(state), timeout=400)

    video_asset = state.get("video_asset")
    if video_asset:
        log_section("Step 11 — assemble_video (PAID — Flora video gen) — SUCCESS", dump(video_asset))
        async with aiohttp.ClientSession() as dl:
            try:
                ext = "mp4"
                path = await download_file(dl, video_asset["url"], f"final_video.{ext}")
                print(f"Downloaded video: {path}", flush=True)
                log_section("Video downloaded", f"Local path: {path}\nModel used: {video_asset.get('model_used')}")
            except Exception as exc:
                log_section("Video download FAILED", f"{exc}")
    else:
        log_section(
            "Step 11 — assemble_video (PAID — Flora video gen) — FAILED, both models",
            f"content_type degraded to: {state.get('content_type')}\n"
            f"No video was produced. Check logs above / console output for the real "
            f"error from each model attempt. This is reported honestly, not hidden."
        )

    from agent.nodes.post import write_post
    state = await asyncio.wait_for(write_post(state), timeout=60)
    log_section("Step 12 — write_post", state.get("post_text") or "(none)")

    with open("STAGE2_REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_SECTIONS))

    # Persist final state too, for reference
    with open("_stage2_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, default=str)

    print("\n\n=== STAGE 2 COMPLETE — see STAGE2_REPORT.md ===", flush=True)
    print(f"Assets: {DOWNLOAD_DIR}", flush=True)


asyncio.run(main())
