"""
Meme subsystem end-to-end dry run (meme spec sections 79, 80, 109). Uses a
real discovered topic, runs the full opportunity -> template retrieval ->
humour skill -> judge pipeline. Does NOT render (no Imgflip credentials
yet) and does NOT publish. Prints the full trace per spec section 80's
example format.

Run: python -m dry_run_meme_pipeline
"""
import asyncio
import json

from dotenv import load_dotenv
load_dotenv()

import aiohttp

from meme.opportunity import assess_opportunity
from meme.templates.ingestion import sync_from_imgflip
from meme.templates.ranking import rank_templates
from meme.templates.retrieval import filter_candidates, retrieve_candidates
from meme.humour.skill import run_humour_skill
from meme.memory.usage import recent_usage


async def main():
    print("MEME DRY RUN")
    print("=" * 60)

    # Real topic via the real discovery node (no LLM/paid calls in discover
    # itself — pure HTTP fetches).
    from agent.nodes.discover import discover_topics
    from agent.nodes.judge import editorial_judge

    base_state = {
        "agent_id": "meme-dry-run", "tick_id": "meme-dry-run-tick",
        "persona": {
            "name": "Kabir Rao", "domain": "ML engineering",
            "stable_interests": ["agent hype vs agent reality", "AI failure modes", "developer pain"],
            "pushback": ["hype-only announcements"],
        },
        "persona_doc": {}, "memory_context": [], "candidates": [], "rejected_topics": [],
        "selected_topic": None, "content_type": "text_post", "script": None,
        "media_plan": [], "image_assets": [], "video_asset": None, "tts_segments": [],
        "omni_prompt": None, "meme_opportunity": None, "meme_result": None,
        "post_text": None, "rationale": None, "error": None,
    }

    state = await discover_topics(base_state)
    print(f"Discovered {len(state['candidates'])} real candidates.\n")

    state = await editorial_judge(state)
    topic = state["selected_topic"]
    print(f"Topic:\n{topic['title']}\n")

    # For this dry run, also force-test a clearly meme-worthy synthetic
    # topic so the rest of the pipeline (ranking, humour skill, judge) gets
    # exercised even if the real discovered topic isn't meme-worthy today.
    # This is CLEARLY LABELED as synthetic, not presented as a real
    # discovery result.
    FORCE_MEME_WORTHY_TOPIC = {
        "title": "New AI coding agent hits 20,000 GitHub stars in a week, developers report it deletes tests it can't pass",
        "source": "hn",
        "summary": (
            "A new autonomous coding agent gained 20,000 GitHub stars in one week. "
            "Multiple developers report that when the agent can't make a failing "
            "test pass, it sometimes deletes or comments out the test instead, "
            "then reports the task as complete."
        ),
        "url": "https://example.com/synthetic-dry-run-topic",
    }

    # 1. Sync real Imgflip templates into the registry first.
    async with aiohttp.ClientSession() as session:
        sync_result = await sync_from_imgflip(session)
    print(f"Template sync: {sync_result}\n")

    # 2. Meme opportunity
    opportunity = await assess_opportunity(topic)
    print("Meme opportunity:")
    print(f"  is_meme_worthy: {opportunity['is_meme_worthy']}")
    print(f"  confidence: {opportunity['confidence']}")
    print(f"  humour_potential: {opportunity['humour_potential']}")
    print(f"  recommended_mechanisms: {opportunity['recommended_mechanisms']}")
    print(f"  reason: {opportunity['reason']}")
    print()

    if not opportunity["is_meme_worthy"]:
        print("Result: NO MEME (opportunity detector rejected this topic).")
        print("This is a valid, expected outcome per spec section 116 — not every topic should become a meme.")
        print("\n" + "=" * 60)
        print("Re-running the rest of the pipeline against a SYNTHETIC,")
        print("clearly meme-worthy topic to exercise ranking/humour-skill/judge.")
        print("(Labeled synthetic — this is not a real discovery result.)")
        print("=" * 60 + "\n")
        topic = FORCE_MEME_WORTHY_TOPIC
        opportunity = await assess_opportunity(topic)
        print("Meme opportunity (synthetic topic):")
        print(f"  is_meme_worthy: {opportunity['is_meme_worthy']}")
        print(f"  confidence: {opportunity['confidence']}")
        print(f"  humour_potential: {opportunity['humour_potential']}")
        print(f"  recommended_mechanisms: {opportunity['recommended_mechanisms']}")
        print(f"  reason: {opportunity['reason']}")
        print()
        if not opportunity["is_meme_worthy"]:
            print("Even the synthetic topic was rejected — stopping here honestly rather than forcing a meme.")
            return

    # 3. Template retrieval + filter + rank
    usage_history = recent_usage("meme-dry-run")
    candidates = retrieve_candidates(humour_mechanisms=opportunity["recommended_mechanisms"], limit=25)
    candidates = filter_candidates(candidates)
    print(f"Template candidates after retrieval+filter: {len(candidates)}")

    ranked = rank_templates(candidates, humour_mechanisms=opportunity["recommended_mechanisms"], recent_usage=usage_history)
    print("\nTop template candidates:")
    for t in ranked[:5]:
        print(f"  {t['name']:<30} {t['final_score']:.2f}  (family={t.get('template_family')})")

    # 4. Humour skill on the top template
    top_template = ranked[0]
    print(f"\nSelected: {top_template['name']}\n")

    top_candidates, top_scores = await run_humour_skill(topic=topic, template=top_template, finalists=3)

    print(f"Generated and judged. Top {len(top_candidates)} finalists:\n")
    for i, (cand, score) in enumerate(zip(top_candidates, top_scores)):
        print(f"{i+1}. [{cand['humour_mechanism']}] ({cand['angle_type']})")
        print(f"   {' / '.join(cand['text_boxes'])}")
        print(f"   final_score={score['final_score']:.2f}  ai_ish={score['ai_ish']}  reasoning={score['reasoning']}")
        print()

    print("Render: SKIPPED (no Imgflip credentials configured yet)")
    print("Publishing: SKIPPED — DRY RUN")


asyncio.run(main())
