"""
ShopMind AI — FastAPI Application Entry Point
"""
 
import logging
import sys
from contextlib import asynccontextmanager
 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
 
from api.routes import router
from utils.storage import init_db
from utils.scraper import BrowserPool
from config.settings import get_settings
 
settings = get_settings()
 
# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
 
 
# ─── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ShopMind AI starting up...")
    await init_db()
    logger.info("Database ready")
    yield
    logger.info("Shutting down — closing browser pool...")
    await BrowserPool.close()
    logger.info("Shutdown complete")
 
 
# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShopMind AI",
    description="Multi-agent product search, comparison, and order placement API",
    version="1.0.0",
    lifespan=lifespan,
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Lock this down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
app.include_router(router, prefix="/api/v1")
 
 
# ─── UI ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def ui():
    return FileResponse("shopmind_ui.html")
 
 
# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
 