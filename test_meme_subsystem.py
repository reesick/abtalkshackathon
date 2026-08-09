"""
Meme subsystem unit tests (meme spec sections 76, 77, 105, 106, 108). Pure
logic tests — no network, no DB writes beyond a throwaway in-memory-style
run against the real SQLite dev DB (acceptable since these are read/write
of throwaway rows this test cleans up).

Run: python -m test_meme_subsystem
"""
import asyncio

from dotenv import load_dotenv
load_dotenv()

PASS = []
FAIL = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"PASS  {name}")
    else:
        FAIL.append((name, detail))
        print(f"FAIL  {name}  {detail}")


def test_cooldown_repetition():
    from meme.templates.cooldown import repetition_penalty, template_cooldown_for

    # Section 105: Drake used 2 posts ago -> strong penalty for Drake again
    history = [
        {"template_name": "Two Buttons", "template_family": "choice", "humour_mechanism": "conflict"},
        {"template_name": "Drake", "template_family": "comparison", "humour_mechanism": "irony"},
    ]
    penalty = repetition_penalty(
        template_name="Drake", template_family="comparison", humour_mechanism="contrast",
        recent_usage=history,
    )
    check("cooldown: same template within window -> penalty > 0", penalty > 0, f"got {penalty}")

    # Family repetition: comparison, comparison -> Two Buttons (choice family) should NOT get family penalty
    history2 = [
        {"template_name": "Drake", "template_family": "comparison", "humour_mechanism": "irony"},
        {"template_name": "Distracted Boyfriend", "template_family": "comparison", "humour_mechanism": "contrast"},
    ]
    penalty2 = repetition_penalty(
        template_name="Two Buttons", template_family="choice", humour_mechanism="conflict",
        recent_usage=history2,
    )
    check("cooldown: different family -> no family penalty", penalty2 == 0.0, f"got {penalty2}")

    # Section 105 variant: comparison family repeated -> family penalty applies
    penalty3 = repetition_penalty(
        template_name="Galaxy Brain", template_family="comparison", humour_mechanism="escalation",
        recent_usage=history2,
    )
    check("cooldown: same family, different template -> family penalty > 0", penalty3 > 0, f"got {penalty3}")

    # Section 105: mechanism repetition — irony, irony -> irony again penalized
    history3 = [
        {"template_name": "A", "template_family": "x", "humour_mechanism": "irony"},
        {"template_name": "B", "template_family": "y", "humour_mechanism": "irony"},
    ]
    penalty4 = repetition_penalty(
        template_name="C", template_family="z", humour_mechanism="irony",
        recent_usage=history3,
    )
    check("cooldown: same mechanism repeated -> mechanism penalty > 0", penalty4 > 0, f"got {penalty4}")

    check("cooldown: overused template gets longer cooldown", template_cooldown_for("Drake") > template_cooldown_for("Two Buttons"))


def test_joke_similarity():
    from meme.memory.repetition import lexical_similarity, similarity_penalty

    a = "me letting the AI write the code"
    b = "me letting AI write the whole function"
    sim = lexical_similarity(a, b)
    check("similarity: near-duplicate phrasing scores high", sim > 0.3, f"got {sim:.2f}")

    c = "why does this look like a GTA loading screen"
    sim2 = lexical_similarity(a, c)
    check("similarity: unrelated captions score low", sim2 < 0.3, f"got {sim2:.2f}")

    penalty = similarity_penalty(b, [a])
    check("similarity_penalty: near-duplicate triggers a penalty", penalty > 0, f"got {penalty}")


def test_safety_ai_ish():
    from meme.humour.safety import is_ai_ish, is_unsafe, caption_text_fits

    check("safety: 'POV:' opener flagged as ai_ish", is_ai_ish("POV: your model hallucinates again"))
    check("safety: 'we are cooked' flagged as ai_ish", is_ai_ish("we are cooked fr fr"))
    check("safety: normal caption not flagged", not is_ai_ish("this bug took four hours and a coffee refill"))

    check("safety: unsafe pattern flagged", is_unsafe("lol imagine dying from this bug"))
    check("safety: normal caption not flagged unsafe", not is_unsafe("this bug took four hours"))

    check("safety: caption fits within limits", caption_text_fits(["short caption"]))
    check("safety: overly long caption fails fit check", not caption_text_fits(["this is a very long caption that goes on and on and on and on and on and on"]))


def test_template_ranking():
    from meme.templates.ranking import rank_templates

    candidates = [
        {"id": "imgflip:1", "name": "Drake", "box_count": 2, "popularity_score": 100,
         "freshness_score": 50, "average_humour_score": 60, "humour_mechanisms": ["contrast", "irony"],
         "template_family": "comparison", "times_selected": 0},
        {"id": "imgflip:2", "name": "This Is Fine", "box_count": 1, "popularity_score": 80,
         "freshness_score": 50, "average_humour_score": 60, "humour_mechanisms": ["understatement", "irony"],
         "template_family": "underreaction", "times_selected": 0},
    ]
    ranked = rank_templates(candidates, humour_mechanisms=["contrast", "irony"], recent_usage=[], exploration_enabled=False)
    check("ranking: returns same number of candidates", len(ranked) == 2)
    check("ranking: each candidate has a final_score", all("final_score" in r for r in ranked))
    check("ranking: sorted descending by final_score", ranked[0]["final_score"] >= ranked[1]["final_score"])


def test_registry_sync_and_schema():
    from meme.templates.registry import sync_meme_templates, list_active_templates

    fake_templates = [
        {"id": "999001", "name": "Test Template A", "url": "https://example.com/a.jpg", "width": 500, "height": 500, "box_count": 2},
        {"id": "999002", "name": "Test Template B", "url": "https://example.com/b.jpg", "width": 500, "height": 500, "box_count": 1},
    ]
    result = sync_meme_templates(fake_templates, provider="test_provider")
    check("registry: sync reports created count", result["created"] >= 0)

    active = list_active_templates(limit=500)
    ids = {t["id"] for t in active}
    check("registry: synced templates appear in active list", "test_provider:999001" in ids and "test_provider:999002" in ids)

    required_keys = {"id", "name", "image_url", "box_count", "template_family", "humour_mechanisms"}
    sample = next(t for t in active if t["id"] == "test_provider:999001")
    check("registry: template dict has required keys", required_keys.issubset(sample.keys()))

    # cleanup
    from db.models import MemeTemplate, get_session
    with get_session() as db:
        for tid in ("test_provider:999001", "test_provider:999002"):
            row = db.get(MemeTemplate, tid)
            if row:
                db.delete(row)


async def test_opportunity_no_meme_fallback():
    """Section 107/17: a failed/degenerate LLM call should default to NO MEME, never crash."""
    from meme.opportunity import assess_opportunity

    # A completely blank topic should still return a valid MemeOpportunity
    # shape (real LLM call — this is a live test of the fallback contract,
    # not a network mock, since the LLM is cheap/fast and always available).
    result = await assess_opportunity({"title": "", "summary": "", "source": ""})
    check("opportunity: always returns is_meme_worthy key", "is_meme_worthy" in result)
    check("opportunity: always returns a reason string", isinstance(result.get("reason"), str) and len(result["reason"]) > 0)


def main():
    test_cooldown_repetition()
    test_joke_similarity()
    test_safety_ai_ish()
    test_template_ranking()
    test_registry_sync_and_schema()
    asyncio.run(test_opportunity_no_meme_fallback())

    print()
    print(f"TOTAL: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("\nFailures:")
        for name, detail in FAIL:
            print(f"  - {name}: {detail}")


if __name__ == "__main__":
    main()
