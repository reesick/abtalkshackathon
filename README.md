# ABTalks Autonomous Agent

Scheduler-driven content pipeline: discovers AI/ML engineering topics → judges them against a persona → generates image/text posts via Flora (nano banana 2 for a single supporting image) → persists to DB + Breeth memory. Runs autonomously for 48h with no per-request generation.

Persona voice, structure, and editorial rules are defined in [`ml_engineer_persona.md`](./ml_engineer_persona.md) — that file is the canonical spec; `agent/prompts/persona.py` and the judge/rationale nodes implement it. Video and TTS are explicitly out of scope for this version (see persona spec section 6) — the code for both still exists (`agent/nodes/video.py`, `agent/nodes/generate_tts.py`, `agent/nodes/omni_prompt.py`) but is disconnected from the graph, left as a clean seam for later.

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

Then seed an agent (first tick fires in ~5 seconds). Example uses Kabir Rao,
the reference persona from `ml_engineer_persona.md`:

```bash
curl -s -X POST http://localhost:8000/api/agent/init \
  -H "Content-Type: application/json" \
  -d '{
    "persona_name": "Kabir Rao",
    "persona_domain": "ML engineering",
    "voice_rules": "terse, story-first, earns the opinion by showing the scar first, no hype",
    "recurring_opinions": [
      "most published benchmarks are marketing, not science",
      "a team that cannot explain its eval methodology in one sentence does not have one",
      "agents are not products, reliability is the product",
      "data cleaning is more valuable than model architecture for 90% of teams",
      "most AI failures are specification failures, not model failures",
      "cost is a feature, if you cannot say what a query costs you, you do not understand your product"
    ],
    "stable_interests": [
      "model evaluation and why most evals lie",
      "GPU and inference cost economics",
      "RAG systems and why they break in the real world",
      "the gap between demo-quality and production-quality AI",
      "hiring signal in ML roles",
      "agent hype vs agent reality",
      "data quality as the unsexy bottleneck",
      "open source vs closed lab dynamics"
    ],
    "pushback": [
      "hype-only announcements with no technical substance",
      "unverified benchmark claims", "leaderboard-only wins"
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
        ├── decide_format     deterministic router → image/text
        ├── write_script      LLM → single visual idea (image_post only)
        ├── generate_assets   Flora: nano banana 2 (one image per post)
        ├── write_post        LLM post in persona voice (hook/turn/contrast/closer)
        ├── generate_rationale structured editorial rationale
        └── persist           DB write + Breeth fingerprint + persona doc delta
```

**`/feed` is read-only.** Generation only happens on the scheduler loop.

### Degradation chain

| Failure | Fallback |
|---|---|
| `generate_assets` fails | `content_type → text_post` (no feed gap) |
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
│       ├── judge.py             Editorial scoring (accept/reject rules)
│       ├── format.py            Deterministic format router (image_post / text_post)
│       ├── script.py            Single-image visual idea writer
│       ├── plan_assets.py       Converts visual idea into a structured asset plan
│       ├── assets.py            Flora → nano banana 2 (one image per post)
│       ├── validate_assets.py   Heuristic asset validation
│       ├── post.py              Post writer (hook/turn/contrast-line/closer structure)
│       ├── rationale.py         Editorial rationale (selected_because/relevant_now_because/...)
│       ├── persist.py           DB + Breeth memory
│       │
│       │   -- disconnected from the graph, out of scope per persona spec
│       │      section 6, kept as a clean seam for later --
│       ├── generate_tts.py      ElevenLabs TTS (not wired in)
│       ├── omni_prompt.py       Video prompt builder (not wired in)
│       └── video.py             Flora video assembly (not wired in)
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
