"""
Renderer provider abstraction (meme spec sections 58, 59, 60). The humour
system should not care which provider renders the final image — only
ImgflipRenderer exists right now, but this keeps the interface stable if a
second provider is added later.
"""
from typing import Optional, Protocol

import aiohttp

from meme.providers import imgflip


class MemeRenderer(Protocol):
    async def render(self, session: aiohttp.ClientSession, *, template_id: str, text_boxes: list[str]) -> Optional[str]:
        ...


class ImgflipRenderer:
    async def render(self, session: aiohttp.ClientSession, *, template_id: str, text_boxes: list[str]) -> Optional[str]:
        return await imgflip.render_with_fallback(session, template_id=template_id, text_boxes=text_boxes)


def get_default_renderer() -> MemeRenderer:
    return ImgflipRenderer()
