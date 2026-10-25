import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.api import infographics, health

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("legal_snaps")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Legal Snaps application...")
    init_db()
    logger.info("Legal Snaps backend ready.")
    yield
    logger.info("Shutting down Legal Snaps backend.")

app = FastAPI(
    title=settings.app_name,
    description="Backend API and pipeline for Legal Snaps Infographic Generator",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
origins = settings.cors_origin_list
if "*" not in origins and "http://localhost:3000" not in origins:
    origins.extend(["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(infographics.router)

@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_url": "/api/health",
        "status": "online"
    }
