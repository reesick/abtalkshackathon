"""
validate_assets node — per spec section 9. Heuristic-first validation
(does the asset have a real output URL, no error) since vision-model
validation is likely blocked by the same Bedrock model-access limits hit
during earlier testing (see MEDIA_PIPELINE_PLAN.md section 9 / 13).

Per spec section 16 failure table: "Missing asset -> Block final Omni
generation until resolved." Implemented here as: assets that fail heuristic
checks are marked rejected and excluded from the plan passed downstream.
"""
import logging

from agent.state import AgentState, MediaAsset

logger = logging.getLogger(__name__)


def _heuristic_check(asset: MediaAsset) -> tuple[bool, str]:
    """
    Cheap, code-level checks only — no vision model call (see plan section 9
    for why). Returns (passed, notes).
    """
    if asset["status"] != "generated":
        return False, f"asset was not successfully generated (status={asset['status']})"
    url = asset.get("output_url")
    if not url or not url.startswith("https://"):
        return False, "missing or invalid output_url"
    if not asset.get("prompt"):
        return False, "no prompt recorded — cannot verify intent"
    return True, "heuristic checks passed (no vision-model verification performed)"


async def validate_assets(state: AgentState) -> AgentState:
    media_plan = state.get("media_plan") or []
    if not media_plan:
        return state

    validated: list[MediaAsset] = []
    for asset in media_plan:
        passed, notes = _heuristic_check(asset)
        updated = {**asset, "validation_notes": notes}
        updated["status"] = "approved" if passed else "rejected"
        validated.append(updated)
        if not passed:
            logger.warning("validate_assets: %s rejected — %s", asset["asset_id"], notes)

    approved_count = sum(1 for a in validated if a["status"] == "approved")
    logger.info("validate_assets: %d/%d assets approved", approved_count, len(validated))

    if approved_count == 0:
        return {**state, "media_plan": validated, "image_assets": [], "content_type": "text_post"}

    image_assets = [
        {"url": a["output_url"], "prompt_used": a["prompt"], "beat_index": i}
        for i, a in enumerate(validated) if a["status"] == "approved"
    ]

    return {**state, "media_plan": validated, "image_assets": image_assets}
