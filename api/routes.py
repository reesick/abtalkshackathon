"""
FastAPI route handlers.

POST /api/agent/init   — create agent, seed Breeth persona doc, start scheduler
GET  /api/agent/feed   — read-only; never triggers generation
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agent.scheduler import start_agent_job
from db.models import Agent, Post, get_session
from mcp_client import get_tool

router = APIRouter(prefix="/api/agent")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    persona_name: str
    persona_domain: str
    voice_rules: str = ""
    recurring_opinions: list[str] = []
    stable_interests: list[str] = []
    pushback: list[str] = []


class InitResponse(BaseModel):
    agentId: str
    message: str


class PostOut(BaseModel):
    id: int
    agent_id: str
    text: str
    media_url: Optional[str]
    media_type: Optional[str]
    content_type: str
    topic_title: Optional[str]
    topic_url: Optional[str]
    rationale: Optional[dict]
    sources: Optional[list[str]]
    created_at: datetime


class FeedResponse(BaseModel):
    agentId: str
    personaName: Optional[str] = None
    personaDomain: Optional[str] = None
    posts: list[PostOut]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_breeth_persona(agent_id: str, req: InitRequest) -> None:
    """
    Write the initial persona definition into Breeth as an episode so
    search_graph can find it for continuity context.
    Uses add_episode (real Breeth tool) — fire and forget (async pipeline).
    """
    try:
        add_tool = get_tool("add_episode")
        persona_text = (
            f"Persona: {req.persona_name}. "
            f"Domain: {req.persona_domain}. "
            f"Voice: {req.voice_rules}. "
            f"Recurring opinions: {'; '.join(req.recurring_opinions)}. "
            f"Interests: {', '.join(req.stable_interests)}. "
            f"Skeptical of: {', '.join(req.pushback)}."
        )
        await add_tool.ainvoke({"text": persona_text})
    except Exception:
        # Non-fatal — graph still runs without a seeded persona episode
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/init", response_model=InitResponse, status_code=201)
async def init_agent(req: InitRequest) -> InitResponse:
    """
    Create a new autonomous agent row, seed its Breeth persona doc, and
    register a scheduler job.  Returns immediately — the first tick fires in ~5s.
    """
    agent_id = str(uuid.uuid4())

    persona = {
        "name": req.persona_name,
        "domain": req.persona_domain,
        "voice_rules": req.voice_rules,
        "recurring_opinions": req.recurring_opinions,
        "stable_interests": req.stable_interests,
        "pushback": req.pushback,
    }

    with get_session() as db:
        agent_row = Agent(
            id=agent_id,
            persona_name=req.persona_name,
            persona_domain=req.persona_domain,
            persona_json=json.dumps(persona),
            created_at=datetime.now(timezone.utc),
        )
        db.add(agent_row)

    # Seed Breeth (non-blocking on failure)
    await _seed_breeth_persona(agent_id, req)

    # Start the scheduler job — fires first tick in ~5s
    start_agent_job(agent_id)

    return InitResponse(
        agentId=agent_id,
        message=f"Agent '{req.persona_name}' initialised. First post in ~5 seconds.",
    )


@router.post("/run")
async def run_tick_now(agentId: str = Query(...)) -> dict:
    """Debug: run one tick immediately and return result or error."""
    import traceback
    from agent.scheduler import _fetch_memory_context
    from agent.graph import run_agent_tick

    with get_session() as db:
        agent_row = db.query(Agent).filter(Agent.id == agentId).first()
        if not agent_row:
            raise HTTPException(status_code=404, detail=f"Agent '{agentId}' not found")
        persona = json.loads(agent_row.persona_json)

    try:
        persona_doc, memory_context = await _fetch_memory_context(agentId)
        await run_agent_tick(agentId, persona, persona_doc, memory_context)
        # check if a post was created
        with get_session() as db:
            from db.models import Post
            post = db.query(Post).filter(Post.agent_id == agentId).order_by(Post.id.desc()).first()
            if post:
                return {"status": "ok", "post_id": post.id, "content_type": post.content_type, "topic": post.topic_title, "text": post.text[:300]}
        return {"status": "ok", "note": "tick ran but no post written — check for silent errors"}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "traceback": traceback.format_exc()}


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    agentId: str = Query(..., description="Agent UUID from /init"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[int] = Query(None, description="Post ID cursor for pagination"),
) -> FeedResponse:
    """
    Read-only feed endpoint.  Never triggers generation.
    Returns posts ordered newest-first with optional cursor pagination.
    """
    return await _get_feed_for_agent(agentId, limit, cursor)


@router.get("/latest-agent")
async def get_latest_agent():
    """Get the most recently created agent."""
    with get_session() as db:
        agent = db.query(Agent).order_by(Agent.created_at.desc()).first()
        if not agent:
            return {"agentId": None}
        return {"agentId": agent.id, "personaName": agent.persona_name}


async def _get_feed_for_agent(agentId: str, limit: int, cursor: Optional[int]) -> FeedResponse:
    """Internal helper to get feed for a specific agent."""
    with get_session() as db:
        agent_row = db.query(Agent).filter(Agent.id == agentId).first()
        if not agent_row:
            raise HTTPException(status_code=404, detail=f"Agent '{agentId}' not found")

        query = db.query(Post).filter(Post.agent_id == agentId)
        if cursor is not None:
            query = query.filter(Post.id < cursor)
        rows = query.order_by(Post.created_at.desc()).limit(limit).all()
        total = db.query(Post).filter(Post.agent_id == agentId).count()

        # Build PostOut objects INSIDE the session to avoid DetachedInstanceError
        posts = [
            PostOut(
                id=r.id,
                agent_id=r.agent_id,
                text=r.text,
                media_url=r.media_url,
                media_type=r.media_type,
                content_type=r.content_type,
                topic_title=r.topic_title,
                topic_url=r.topic_url,
                rationale=json.loads(r.rationale) if r.rationale else None,
                sources=json.loads(r.sources) if r.sources else None,
                created_at=r.created_at,
            )
            for r in rows
        ]

        persona_name = agent_row.persona_name
        persona_domain = agent_row.persona_domain

    return FeedResponse(
        agentId=agentId,
        personaName=persona_name,
        personaDomain=persona_domain,
        posts=posts,
        total=total
    )
