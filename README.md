# ABTalks Autonomous Agent

Scheduler-driven content pipeline: discovers AI/tech topics → judges them against a persona → generates video/image/text posts via Flora MCP (nano banana 2 + Google Omni) → persists to DB + Breeth memory. Runs autonomously for 48h with no per-request generation.

---

## Quick start

```bash
cd abtalks
pip install -r requirements.txt
uvicorn main:app --reload
```

First, check what tool names your MCP servers actually expose:

```bash
python check_tools.py
```

Then seed an agent (first tick fires in ~5 seconds):

```bash
curl -s -X POST http://localhost:8000/api/agent/init \
  -H "Content-Type: application/json" \
  -d '{
    "persona_name": "Ada Shen",
    "persona_domain": "ML infrastructure",
    "voice_rules": "terse, technically skeptical, avoids hype",
    "recurring_opinions": [
      "skeptical of benchmark-only claims",
      "pro open-weights"
    ],
    "stable_interests": [
      "inference efficiency", "model serving", "open source tooling"
    ],
    "pushback": [
      "hype-only announcements", "closed-source-only research"
    ]
  }'
```

Poll the feed:

```bash
curl "http://localhost:8000/api/agent/feed?agentId=<id from above>"
```

---

## Environment (.env)

| Variable | Required | Notes |
|---|---|---|
| `BREETH_MCP_URL` | ✅ | `https://mcp.thebreeth.com/mcp` |
| `BREETH_API_KEY` | ✅ | `ck_live_...` |
| `AWS_ACCESS_KEY_ID` | ✅ | Bedrock key ID |
| `AWS_SECRET_ACCESS_KEY` | ✅ | Bedrock secret |
| `AWS_REGION` | ✅ | default `us-east-1` |
| `FLORA_MCP_URL` | when ready | Flora MCP endpoint |
| `FLORA_API_KEY` | when ready | Flora Bearer token |
| `DATABASE_URL` | optional | default: `sqlite:///./abtalks.db` |

---

## Architecture

```
Scheduler (150-240 min jitter)
  └── LangGraph tick
        ├── discover_topics   RSS + HN Algolia + Reddit .json
        ├── filter_seen       Breeth near-duplicate filter
        ├── editorial_judge   LLM scoring, logs all rejections
        ├── decide_format     deterministic router → video/image/text
        ├── write_script      LLM → hook/beats/narration
        ├── generate_assets   Flora: nano banana 2 (one frame per beat)
        ├── assemble_video    Flora: Google Omni (frames + VO → mp4)
        ├── write_post        LLM caption in persona voice
        ├── generate_rationale structured editorial rationale
        └── persist           DB write + Breeth fingerprint + persona doc delta
```

**`/feed` is read-only.** Generation only happens on the scheduler loop.

### Degradation chain

| Failure | Fallback |
|---|---|
| `assemble_video` timeout / error | `content_type → image_post` (first frame as media) |
| `generate_assets` all frames fail | `content_type → text_post` (no feed gap) |
| Breeth unavailable | pass-through (filter + memory skip silently) |
| No candidates after filter | clean exit, `tick_log` row: `published=False` |

---

## API

### `POST /api/agent/init`
Creates agent, seeds Breeth persona doc, starts scheduler.
Returns `{ agentId }` immediately. First tick in ~5s.

### `GET /api/agent/feed?agentId=&limit=&cursor=`
Read-only. Returns `{ agentId, posts[], total }`.
Each post includes `text`, `mediaUrl`, `mediaType`, `rationale`, `sources`, `createdAt`.

### `GET /health`
Returns `{ status: "ok" }`.

---

## File structure

```
abtalks/
├── main.py                      FastAPI app + lifespan
├── mcp_client.py                MultiServerMCPClient (Flora + Breeth)
├── check_tools.py               Print all MCP tool names (run before first deploy)
├── requirements.txt
├── Procfile                     Render/Railway deploy
├── .env                         Secrets (never commit)
├── .gitignore
├── agent/
│   ├── llm.py                   Bedrock LLM factory (all nodes import from here)
│   ├── state.py                 AgentState TypedDict
│   ├── graph.py                 StateGraph + conditional edges
│   ├── scheduler.py             APScheduler, jittered 150-240 min
│   ├── prompts/
│   │   └── persona.py           System prompt template (all sections)
│   └── nodes/
│       ├── discover.py          RSS + HN + Reddit
│       ├── filter.py            Breeth dedup filter
│       ├── judge.py             Editorial scoring
│       ├── format.py            Deterministic format router
│       ├── script.py            Video script writer
│       ├── assets.py            Flora → nano banana 2
│       ├── video.py             Flora → Google Omni
│       ├── post.py              Caption writer
│       ├── rationale.py         Editorial rationale
│       └── persist.py           DB + Breeth memory
├── api/
│   └── routes.py                /init and /feed endpoints
└── db/
    └── models.py                Agent, Post, TickLog tables
```

---

## Before the 48h window: one required step

Run `python check_tools.py` and compare the printed tool names against the
placeholder names in the nodes. Breeth and Flora use their own naming conventions
and the placeholders (`breeth_search_memory`, `nano_banana_2_generate`, etc.) must
match exactly. The `check_tools.py` output tells you exactly what to fix.
