import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter
from app.config import settings
from app.schemas import HealthCheckResponse

router = APIRouter(prefix="/api/health", tags=["Health"])

@router.get("", response_model=HealthCheckResponse)
async def check_health():
    # Test storage directory write permission
    storage_writable = False
    try:
        test_file = Path(settings.storage_dir) / ".health_test"
        test_file.write_text("ok")
        if test_file.exists():
            test_file.unlink()
            storage_writable = True
    except Exception:
        storage_writable = False

    # Test resvg renderer availability
    renderer_available = False
    try:
        import resvg_py
        test_bytes = resvg_py.svg_to_bytes('<svg width="10" height="10" xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" fill="black"/></svg>')
        renderer_available = len(test_bytes) > 0
    except Exception:
        renderer_available = False

    provider_configured = bool(settings.get_effective_hf_token())

    return HealthCheckResponse(
        status="healthy" if (storage_writable and renderer_available) else "degraded",
        app_name=settings.app_name,
        ai_provider="Hugging Face Inference Providers",
        provider_configured=provider_configured,
        analysis_model=settings.hf_text_model,
        image_model=settings.hf_image_model,
        search_provider=settings.search_provider,
        ocr_provider=settings.ocr_provider,
        renderer_available=renderer_available,
        storage_writable=storage_writable,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
