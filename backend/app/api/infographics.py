import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, Response
from app.config import settings
from app.database import create_job, get_job, list_jobs, delete_job
from app.schemas import (
    InfographicCreateRequest,
    JobResponse,
    JobListItem,
    JobStage,
    STAGE_NAMES
)
from app.pipeline.orchestrator import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/infographics", tags=["Infographics"])

def build_job_response(job: dict) -> JobResponse:
    stage_idx = job.get("current_stage", 0)
    stage_name = STAGE_NAMES.get(stage_idx, "")
    
    storage_dir = Path(settings.storage_dir)
    svg_fn = job.get("svg_filename")
    png_fn = job.get("png_filename")
    artwork_fn = job.get("artwork_filename")

    has_svg = bool(svg_fn and (storage_dir / svg_fn).is_file())
    has_png = bool(png_fn and (storage_dir / png_fn).is_file())
    has_artwork = bool(artwork_fn and (storage_dir / artwork_fn).is_file())

    record = job.get("legal_record") or {}

    return JobResponse(
        job_id=job["job_id"],
        status=job.get("status", JobStage.IDLE),
        current_stage=stage_idx,
        current_stage_name=stage_name,
        progress_percent=job.get("progress_percent", 0),
        error_message=job.get("error_message"),
        created_at=job.get("created_at", ""),
        updated_at=job.get("updated_at", ""),
        article_name=job.get("article_name"),
        article_url=job.get("article_url") or job.get("pdf_url"),
        output_format=job.get("output_format", "both"),
        enable_image_generation=job.get("enable_image_generation", False),
        source_metadata=job.get("source_metadata"),
        legal_record=job.get("legal_record"),
        validation_summary=job.get("validation_summary"),
        content_plan=job.get("content_plan"),
        svg_filename=svg_fn,
        png_filename=png_fn,
        artwork_filename=artwork_fn if has_artwork else None,
        has_svg=has_svg,
        has_png=has_png,
        artwork_generated=has_artwork,
        analysis_source=record.get("analysis_source"),
        warnings=job.get("warnings") or [],
        logs=job.get("logs") or []
    )

@router.post("", response_model=JobResponse, status_code=202)
async def create_infographic_job(
    request: InfographicCreateRequest,
    background_tasks: BackgroundTasks
):
    """
    Validate input and launch an asynchronous 10-stage legal infographic generation job.
    Does not block the HTTP connection.
    """
    try:
        request.validate_input_present()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "status": JobStage.IDLE.value,
        "current_stage": 0,
        "progress_percent": 0,
        "article_name": request.article_name,
        "article_url": request.article_url,
        "pdf_url": request.pdf_url,
        "language": request.language,
        "output_format": request.output_format,
        "enable_image_generation": request.enable_image_generation,
        "width": request.width,
        "height": request.height,
        "logs": [f"Job created with output format '{request.output_format}' ({request.width}x{request.height}px)"],
        "warnings": []
    }

    created = create_job(job_record)
    # Launch background task
    background_tasks.add_task(run_pipeline, job_id)

    return build_job_response(created)

@router.get("", response_model=List[JobListItem])
async def list_infographics(limit: int = Query(50, ge=1, le=100)):
    """Retrieve history of saved infographic generation jobs."""
    jobs = list_jobs(limit=limit)
    storage_dir = Path(settings.storage_dir)
    items = []
    
    for j in jobs:
        svg_fn = j.get("svg_filename")
        png_fn = j.get("png_filename")
        has_svg = bool(svg_fn and (storage_dir / svg_fn).is_file())
        has_png = bool(png_fn and (storage_dir / png_fn).is_file())
        
        plan = j.get("content_plan") or {}
        val = j.get("validation_summary") or {}
        
        items.append(JobListItem(
            job_id=j["job_id"],
            status=j.get("status", JobStage.IDLE),
            article_name=j.get("article_name"),
            created_at=j.get("created_at", ""),
            updated_at=j.get("updated_at", ""),
            has_svg=has_svg,
            has_png=has_png,
            headline=plan.get("headline"),
            court_case_info=plan.get("court_case_info"),
            validation_verified_count=val.get("verified_claims", 0),
            validation_total_count=val.get("total_claims", 0)
        ))
    return items

@router.get("/{job_id}", response_model=JobResponse)
async def get_infographic_status(job_id: str):
    """Retrieve full generation status, intermediate legal facts, validation audit, and logs."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Infographic job '{job_id}' not found.")
    return build_job_response(job)

@router.get("/{job_id}/preview")
async def get_infographic_preview(job_id: str, format: Optional[str] = Query(None)):
    """
    Returns inline preview of the generated artifact.
    Can specify format=png or format=svg.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
        
    storage_dir = Path(settings.storage_dir)
    svg_fn = job.get("svg_filename")
    png_fn = job.get("png_filename")
    
    if format == "png" and png_fn:
        png_path = storage_dir / png_fn
        if png_path.is_file():
            return FileResponse(
                path=str(png_path),
                media_type="image/png",
                headers={"Cache-Control": "no-cache"}
            )
            
    if (format == "svg" or not format) and svg_fn:
        svg_path = storage_dir / svg_fn
        if svg_path.is_file():
            return Response(
                content=svg_path.read_text(encoding="utf-8"),
                media_type="image/svg+xml",
                headers={"Cache-Control": "no-cache"}
            )
            
    if png_fn:
        png_path = storage_dir / png_fn
        if png_path.is_file():
            return FileResponse(
                path=str(png_path),
                media_type="image/png",
                headers={"Cache-Control": "no-cache"}
            )
            
    raise HTTPException(status_code=404, detail="Infographic preview artifact not yet available.")

@router.get("/{job_id}/download/svg")
async def download_svg(job_id: str):
    """Download the generated standalone SVG file."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
        
    svg_fn = job.get("svg_filename")
    if not svg_fn:
        raise HTTPException(status_code=404, detail="SVG artifact has not been generated for this job.")
        
    svg_path = Path(settings.storage_dir) / svg_fn
    if not svg_path.is_file():
        raise HTTPException(status_code=404, detail="SVG file missing from storage.")

    safe_title = "".join(c for c in (job.get("article_name") or "legal_snap") if c.isalnum() or c in "-_")
    filename = f"{safe_title}_{job_id[:8]}.svg"

    return FileResponse(
        path=str(svg_path),
        filename=filename,
        media_type="image/svg+xml"
    )

@router.get("/{job_id}/download/png")
async def download_png(job_id: str):
    """Download the rendered high-resolution PNG file."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
        
    png_fn = job.get("png_filename")
    if not png_fn:
        raise HTTPException(status_code=404, detail="PNG artifact has not been rendered for this job.")
        
    png_path = Path(settings.storage_dir) / png_fn
    if not png_path.is_file():
        raise HTTPException(status_code=404, detail="PNG file missing from storage.")

    safe_title = "".join(c for c in (job.get("article_name") or "legal_snap") if c.isalnum() or c in "-_")
    filename = f"{safe_title}_{job_id[:8]}.png"

    return FileResponse(
        path=str(png_path),
        filename=filename,
        media_type="image/png"
    )

@router.delete("/{job_id}", status_code=204)
async def delete_infographic_artifact(job_id: str):
    """Delete a generated infographic artifact and its database record."""
    success = delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or already deleted.")
    return Response(status_code=204)
