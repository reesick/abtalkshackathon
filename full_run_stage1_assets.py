"""
STAGE 1 — fires discover -> ... -> generate_assets (PAID, images) ->
validate_assets -> generate_tts (PAID, audio). Downloads all images + audio
to local disk. STOPS before assemble_video (video generation) — that is a
separate, explicit step (see full_run_stage2_video.py) fired only after
reviewing this stage's output.
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
    REPORT_SECTIONS.append(f"# Media Pipeline STAGE 1 (images + audio, paid)\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n")

    state = dict(BASE_STATE)

    from agent.nodes.discover import discover_topics
    state = await asyncio.wait_for(discover_topics(state), timeout=30)
    log_section("Step 1 — discover_topics", f"{len(state['candidates'])} candidates found")

    from agent.nodes.filter import filter_seen
    from mcp_client import init_mcp_client
    await init_mcp_client()
    state = await asyncio.wait_for(filter_seen(state), timeout=60)
    log_section("Step 2 — filter_seen", f"{len(state['candidates'])} candidates after filter")

    from agent.nodes.judge import editorial_judge
    state = await asyncio.wait_for(editorial_judge(state), timeout=60)
    selected = state.get("selected_topic") or {}
    log_section("Step 3 — editorial_judge", dump(selected))

    from agent.nodes.format import decide_format
    state = decide_format(state)
    log_section("Step 4 — decide_format", f"Router picked: {state['content_type']} — forcing video_post")
    state["content_type"] = "video_post"

    from agent.nodes.script import write_script
    state = await asyncio.wait_for(write_script(state), timeout=60)
    narration = state["script"].get("narration", "")
    log_section("Step 5 — write_script", f"{dump(state['script'])}\n\nNarration word count: {len(narration.split())}")

    from agent.nodes.plan_assets import plan_media_assets
    state = await asyncio.wait_for(plan_media_assets(state), timeout=60)
    log_section("Step 6 — plan_media_assets", dump(state["media_plan"]))

    print("\n\n*** FIRING PAID CALL: generate_assets (Flora image gen) ***\n", flush=True)
    from agent.nodes.assets import generate_assets
    state = await asyncio.wait_for(generate_assets(state), timeout=180)
    log_section(
        "Step 7 — generate_assets (PAID — Flora image gen)",
        dump([{k: v for k, v in a.items() if k != "reference_asset"} for a in state["media_plan"]])
    )

    from agent.nodes.validate_assets import validate_assets
    state = await asyncio.wait_for(validate_assets(state), timeout=30)
    approved = [a for a in state["media_plan"] if a["status"] == "approved"]
    log_section("Step 8 — validate_assets", f"{len(approved)}/{len(state['media_plan'])} approved")

    if not approved:
        log_section("ABORTED", "No approved assets.")
        with open("STAGE1_REPORT.md", "w", encoding="utf-8") as f:
            f.write("\n".join(REPORT_SECTIONS))
        return

    async with aiohttp.ClientSession() as dl:
        for a in approved:
            try:
                path = await download_file(dl, a["output_url"], f"{a['asset_id']}.png")
                print(f"Downloaded image: {path}", flush=True)
            except Exception as exc:
                print(f"Failed to download {a['asset_id']}: {exc}", flush=True)

    print("\n\n*** FIRING PAID CALL: generate_tts (ElevenLabs) ***\n", flush=True)
    from agent.nodes.generate_tts import generate_tts
    state = await asyncio.wait_for(generate_tts(state), timeout=60)
    log_section("Step 9 — generate_tts (PAID — ElevenLabs)", dump(state["tts_segments"]))

    async with aiohttp.ClientSession() as dl:
        for t in state["tts_segments"]:
            try:
                path = await download_file(dl, t["audio_url"], f"tts_{t['scene_id']}.mp3")
                print(f"Downloaded audio: {path}", flush=True)
            except Exception as exc:
                print(f"Failed to download tts {t['scene_id']}: {exc}", flush=True)

    from agent.nodes.omni_prompt import build_omni_prompt
    state = build_omni_prompt(state)
    log_section("Step 10 — build_omni_prompt (preview, no video fired yet)", "```\n" + (state.get("omni_prompt") or "(none)") + "\n```")

    # Persist state to disk so stage 2 can resume without re-firing paid calls
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, default=str)

    log_section(
        "STOPPED — awaiting go-ahead for video generation",
        f"Images and audio generated and downloaded to `{DOWNLOAD_DIR}`.\n"
        f"State persisted to `{STATE_FILE}` for stage 2.\n"
        f"Run `full_run_stage2_video.py` after reviewing the assets above to fire "
        f"video generation (tries Gemini-Omni-Flash first, falls back to Seedance "
        f"2.0 Reference (Fast) automatically)."
    )

    with open("STAGE1_REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_SECTIONS))

    print("\n\n=== STAGE 1 COMPLETE — see STAGE1_REPORT.md ===", flush=True)
    print(f"Assets: {DOWNLOAD_DIR}", flush=True)


asyncio.run(main())
