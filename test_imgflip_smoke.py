"""
Live Imgflip smoke test (meme spec section 78). Does NOT publish anything.
If credentials are absent, reports SKIP honestly — never fakes a PASS.

Run: python -m test_imgflip_smoke
"""
import asyncio

from dotenv import load_dotenv
load_dotenv()

import aiohttp

from meme.providers import imgflip


async def main():
    print("IMGFLIP LIVE SMOKE TEST")
    print("=" * 50)

    async with aiohttp.ClientSession() as session:
        # 1. fetch templates — free endpoint, no auth needed
        try:
            templates = await imgflip.get_memes(session)
            print(f"1. fetch templates: PASS — {len(templates)} templates returned")
        except imgflip.ImgflipError as exc:
            print(f"1. fetch templates: FAIL — {exc}")
            return

        # 2. select one known template
        drake = next((t for t in templates if t["name"] == "Drake Hotline Bling"), templates[0] if templates else None)
        if not drake:
            print("2. select known template: FAIL — no templates available")
            return
        print(f"2. select known template: PASS — using '{drake['name']}' (id={drake['id']})")

        # 3. render one test meme — requires credentials
        if not imgflip.credentials_configured():
            print("3. render test meme: SKIP — IMGFLIP_USERNAME/IMGFLIP_PASSWORD not configured")
            print("4. validate returned URL: SKIP — depends on step 3")
            print("5. publish: SKIPPED (never attempted, per spec section 78)")
            print()
            print("Result: partial — provider fetch confirmed live and working,")
            print("rendering not exercised because no credentials are configured yet.")
            return

        try:
            url = await imgflip.caption_image(
                session,
                template_id=drake["id"],
                text_boxes=["smoke test top text", "smoke test bottom text"],
            )
            print(f"3. render test meme: PASS — {url}")
        except imgflip.ImgflipError as exc:
            print(f"3. render test meme: FAIL — {exc}")
            return

        # 4. validate returned URL
        valid = url.startswith("https://i.imgflip.com/")
        print(f"4. validate returned URL: {'PASS' if valid else 'FAIL'} — {url}")

        print("5. publish: SKIPPED (never attempted, per spec section 78)")


asyncio.run(main())
