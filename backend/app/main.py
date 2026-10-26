import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# Mount Frontend Static Build (All-in-One Deployment)
possible_frontend_dirs = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "out"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
    "/app/frontend/out",
]

frontend_dist = None
for d in possible_frontend_dirs:
    if os.path.isdir(d) and os.path.isfile(os.path.join(d, "index.html")):
        frontend_dist = d
        break

if frontend_dist:
    logger.info(f"Mounting frontend static build from: {frontend_dist}")
    next_dir = os.path.join(frontend_dist, "_next")
    if os.path.isdir(next_dir):
        app.mount("/_next", StaticFiles(directory=next_dir), name="next_static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            return {"detail": "Not Found"}
        target_file = os.path.join(frontend_dist, full_path)
        if os.path.isfile(target_file):
            return FileResponse(target_file)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"detail": "Not Found"}
else:
    @app.get("/")
    async def root():
        return {
            "app": settings.app_name,
            "version": "1.0.0",
            "docs_url": "/docs",
            "health_url": "/api/health",
            "status": "online"
        }
