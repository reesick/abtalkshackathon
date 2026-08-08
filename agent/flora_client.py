"""
Flora REST API client — server-side, key-authenticated (NOT the MCP/OAuth
flow, which is wrong for this unattended scheduler use case; see
MEDIA_PIPELINE_PLAN.md section 0 for why).

Confirmed working end-to-end tonight against the real account:
  - POST /generate (image, is2i-gemini-3.1-flash-image, params.image_urls)
  - GET  /runs/{run_id} polling
  - POST /assets (signed upload) -> GCS multipart upload -> POST /assets/{id}/complete
"""
import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

FLORA_API_BASE = os.environ.get("FLORA_API_BASE", "https://app.flora.ai/api/v1")
FLORA_API_KEY = os.environ["FLORA_API_KEY"]
FLORA_WORKSPACE_ID = os.environ["FLORA_WORKSPACE_ID"]
FLORA_PROJECT_ID = os.environ["FLORA_PROJECT_ID"]

_AUTH_HEADER = {"Authorization": f"Bearer {FLORA_API_KEY}"}

POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 180  # covers video gen (~70s estimate) with margin


class FloraGenerationError(Exception):
    """Raised when a Flora run fails or times out."""


async def create_generation(
    session: aiohttp.ClientSession,
    *,
    gen_type: str,
    prompt: str,
    model: str,
    params: Optional[dict] = None,
) -> dict:
    """POST /generate — returns the initial response (contains run_id, poll_url)."""
    payload: dict[str, Any] = {
        "type": gen_type,
        "prompt": prompt,
        "workspace_id": FLORA_WORKSPACE_ID,
        "project_id": FLORA_PROJECT_ID,
        "model": model,
    }
    if params:
        payload["params"] = params

    async with session.post(
        f"{FLORA_API_BASE}/generate",
        json=payload,
        headers=_AUTH_HEADER,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        data = await resp.json()
        if resp.status not in (200, 201):
            raise FloraGenerationError(f"generate failed: {resp.status} {data}")
        return data


async def poll_run(session: aiohttp.ClientSession, run_id: str) -> dict:
    """Poll GET /runs/{run_id} until completed or failed. Raises on failure/timeout."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECONDS:
        async with session.get(
            f"{FLORA_API_BASE}/runs/{run_id}",
            headers=_AUTH_HEADER,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()

        status = data.get("status")
        if status == "completed":
            return data
        if status == "failed":
            raise FloraGenerationError(
                f"run {run_id} failed: {data.get('error_code')} {data.get('error_message')}"
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    raise FloraGenerationError(f"run {run_id} timed out after {POLL_TIMEOUT_SECONDS}s")


async def generate_and_wait(
    session: aiohttp.ClientSession,
    *,
    gen_type: str,
    prompt: str,
    model: str,
    params: Optional[dict] = None,
) -> dict:
    """Convenience wrapper: create_generation + poll_run. Returns the completed run data."""
    created = await create_generation(session, gen_type=gen_type, prompt=prompt, model=model, params=params)
    run_id = created["run_id"]
    logger.info("flora_client: run %s created (model=%s, type=%s)", run_id, model, gen_type)
    result = await poll_run(session, run_id)
    logger.info("flora_client: run %s completed", run_id)
    return result


async def upload_asset(
    session: aiohttp.ClientSession,
    *,
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    folder: str = "api-uploads",
) -> str:
    """
    Upload raw bytes (e.g. TTS audio) to Flora and return the permanent HTTPS URL.
    Full 3-step flow: reserve signed upload -> POST bytes to GCS -> mark complete.
    """
    # Step 1: reserve signed upload slot
    async with session.post(
        f"{FLORA_API_BASE}/assets",
        json={
            "source": "signed-url",
            "workspace_id": FLORA_WORKSPACE_ID,
            "file_name": file_name,
            "content_type": content_type,
            "folder": folder,
        },
        headers=_AUTH_HEADER,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        reservation = await resp.json()
        if resp.status not in (200, 201):
            raise FloraGenerationError(f"asset reservation failed: {resp.status} {reservation}")

    asset_id = reservation["asset_id"]
    upload = reservation["upload"]

    # Step 2: upload bytes to the signed GCS URL as multipart form data
    form = aiohttp.FormData()
    for key, value in upload["form_fields"].items():
        form.add_field(key, value)
    form.add_field(upload["file_field"], file_bytes, filename=file_name, content_type=content_type)

    async with session.post(
        upload["url"],
        data=form,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as resp:
        if resp.status not in (200, 201, 204):
            body = await resp.text()
            raise FloraGenerationError(f"asset upload failed: {resp.status} {body}")

    # Step 3: mark complete
    # Flora's /complete endpoint requires a JSON body even though it takes no
    # fields — an empty aiohttp request body (no json=/data=) fails with
    # 400 invalid_json. Confirmed via isolated testing: json={} succeeds.
    async with session.post(
        f"{FLORA_API_BASE}/assets/{asset_id}/complete",
        headers=_AUTH_HEADER,
        json={},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        completed = await resp.json()
        if resp.status not in (200, 201):
            raise FloraGenerationError(f"asset complete failed: {resp.status} {completed}")

    if completed.get("status") != "ready":
        raise FloraGenerationError(f"asset {asset_id} not ready: {completed}")

    logger.info("flora_client: uploaded asset %s -> %s", asset_id, completed["url"])
    return completed["url"]
