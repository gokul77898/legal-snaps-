from typing import Optional
import httpx
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Query
from app.config import settings
from app.schemas import HealthCheckResponse

router = APIRouter(prefix="/api/health", tags=["Health"])

@router.get("", response_model=HealthCheckResponse)
async def check_health(verify_api: bool = Query(False, description="Verify actual HF API request")):
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

    token = settings.get_effective_hf_token()
    provider_configured = bool(token)
    provider_error: Optional[str] = None

    if not provider_configured:
        provider_error = "HF_TOKEN is not configured in backend/.env"
    elif verify_api:
        # Perform actual API request verification to Hugging Face Inference router
        try:
            url = f"{settings.hf_router_base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    provider_error = f"HF API returned status {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            provider_error = f"HF API request failed: {e}"

    is_healthy = storage_writable and renderer_available and provider_configured and not provider_error

    return HealthCheckResponse(
        status="healthy" if is_healthy else "degraded",
        app_name=settings.app_name,
        ai_provider="Hugging Face Inference Providers",
        provider_configured=provider_configured,
        analysis_model=settings.hf_text_model,
        image_model=settings.hf_image_model,
        search_provider=settings.search_provider,
        ocr_provider=settings.ocr_provider,
        renderer_available=renderer_available,
        storage_writable=storage_writable,
        timestamp=datetime.now(timezone.utc).isoformat(),
        provider_error=provider_error,
    )
