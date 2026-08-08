"""
FastAPI application entry point.

Lifespan:
  startup  → load .env, create DB tables, init MCP client
  shutdown → nothing special needed for single-dyno demo
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # must run before any os.environ reads

from fastapi import FastAPI

from api.routes import router
from db.models import create_tables
from mcp_client import init_mcp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    create_tables()
    await init_mcp_client()
    yield
    # --- shutdown ---
    # APScheduler and aiohttp sessions stop with the process


app = FastAPI(
    title="ABTalks Autonomous Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
