"""
Dry-run harness for the current pipeline (Kabir Rao persona, text +
single static image only — see ml_engineer_persona.md). Runs the REAL node
functions (discover -> filter -> judge -> decide_format -> [write_script ->
plan_media_assets] -> write_post -> generate_rationale) and STOPS before
generate_assets — i.e. stops before the one paid API call in this graph
(Flora image gen).

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
        "name": "Kabir Rao",
        "domain": "ML engineering",
        "voice_rules": "terse, story-first, earns the opinion by showing the scar first, no hype",
        "recurring_opinions": [
            "most published benchmarks are marketing, not science",
            "a team that cannot explain its eval methodology in one sentence does not have one",
            "agents are not products, reliability is the product",
            "data cleaning is more valuable than model architecture for 90% of teams",
            "most AI failures are specification failures, not model failures",
            "cost is a feature, if you cannot say what a query costs you, you do not understand your product",
        ],
        "stable_interests": [
            "model evaluation and why most evals lie",
            "GPU and inference cost economics",
            "RAG systems and why they break in the real world",
            "the gap between demo-quality and production-quality AI",
            "hiring signal in ML roles",
            "agent hype vs agent reality",
            "data quality as the unsexy bottleneck",
            "open source vs closed lab dynamics",
        ],
        "pushback": [
            "hype-only announcements with no technical substance",
            "unverified benchmark claims",
            "leaderboard-only wins",
        ],
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
        "Persona: Kabir Rao (ML engineering) — see ml_engineer_persona.md, the "
        "canonical spec this pipeline implements. Scope: text + single static "
        "image per post only (video/TTS out of scope, disconnected from the "
        "graph — see agent/graph.py header comment).\n\n"
        "This run executes discover_topics -> filter_seen -> editorial_judge -> "
        "decide_format -> [write_script -> plan_media_assets, image_post path "
        "only] -> write_post -> generate_rationale using the REAL node code. "
        "It deliberately STOPS before generate_assets (Flora image gen $) — "
        "the only paid API call in this graph — and instead previews the "
        "exact prompt that call would send, using the real pure-function "
        "prompt builder.\n"
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
        f"Detected content_type (deterministic router, image_post/text_post "
        f"only — no video routing exists anymore): {detected_format}"
    )

    if detected_format == "image_post":
        # --- Step 5: write_script (single visual idea) ---
        from agent.nodes.script import write_script
        state = await asyncio.wait_for(write_script(state), timeout=60)
        log_section(
            "Step 5 — write_script",
            f"Input: content_type=image_post, topic={selected.get('title', '')}\n\n"
            f"Output — script (hook + one visual idea):\n{dump(state.get('script'))}"
        )

        # --- Step 6: plan_media_assets ---
        from agent.nodes.plan_assets import plan_media_assets
        state = await asyncio.wait_for(plan_media_assets(state), timeout=60)
        log_section(
            "Step 6 — plan_media_assets",
            f"Input: {len(state['script'].get('beats', []))} script beat(s)\n\n"
            f"Output — media_plan ({len(state['media_plan'])} planned asset(s), "
            f"should be exactly 1 for the single-image-per-post scope):\n"
            + dump(state["media_plan"])
        )

        # --- STOP HERE — next real node is generate_assets (Flora $) ---
        from agent.nodes.assets import build_asset_prompt
        preview_prompts = [
            {"asset_id": a["asset_id"], "would_send_prompt": build_asset_prompt(a)}
            for a in state["media_plan"]
        ]
        log_section(
            "STOPPED — before paid generation call",
            "`generate_assets` was NOT executed — it calls the Flora REST "
            "`/generate` endpoint (Nano Banana 2 image gen, real cost per "
            "call). Below is the exact prompt it would send, built by the "
            "real `build_asset_prompt()` pure function — no API call made.\n\n"
            + dump(preview_prompts)
        )

        # write_post needs *some* image_assets to reference — use a clearly
        # labeled placeholder URL (not real, no Flora call made) so the
        # caption-writing prompt runs exactly as it would post-generation.
        state["image_assets"] = [
            {
                "url": f"<PLACEHOLDER_NOT_REAL_would_be_flora_image_url_for_{a['asset_id']}>",
                "prompt_used": a["prompt"] if a.get("prompt") else preview_prompts[i]["would_send_prompt"],
                "beat_index": i,
            }
            for i, a in enumerate(state["media_plan"])
        ]
    else:
        log_section(
            "Skipped — write_script / plan_media_assets / generate_assets",
            "Router picked text_post, which skips the script/asset nodes "
            "entirely in the real graph (see agent/graph.py _after_format)."
        )

    # --- write_post (real LLM call, no paid media API) ---
    from agent.nodes.post import write_post
    state = await asyncio.wait_for(write_post(state), timeout=60)
    log_section(
        "Step 7 — write_post",
        f"Input: content_type={state['content_type']}\n\n"
        f"Output — post_text (real LLM call, Kabir Rao voice, sanitized for "
        f"banned patterns per ml_engineer_persona.md section 5):\n\n"
        + state.get("post_text", "(none)")
    )

    # --- generate_rationale (real LLM call) ---
    from agent.nodes.rationale import generate_rationale
    state = await asyncio.wait_for(generate_rationale(state), timeout=60)
    log_section(
        "Step 8 — generate_rationale",
        "Output — rationale (section 8 template: selected_because / "
        "relevant_now_because / rejected_alternatives / sources):\n\n"
        + dump(state.get("rationale"))
    )

    # Write the report
    report_text = "\n".join(REPORT_SECTIONS)
    with open("DRY_RUN_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n\n=== DRY RUN COMPLETE — see DRY_RUN_REPORT.md ===", flush=True)


asyncio.run(main())
