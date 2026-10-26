import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.sqlite_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    Path(settings.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS infographic_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                current_stage INTEGER DEFAULT 0,
                progress_percent INTEGER DEFAULT 0,
                article_name TEXT,
                article_url TEXT,
                pdf_url TEXT,
                language TEXT DEFAULT 'en',
                output_format TEXT DEFAULT 'both',
                enable_image_generation INTEGER DEFAULT 0,
                width INTEGER DEFAULT 1200,
                height INTEGER DEFAULT 1200,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT,
                source_metadata TEXT,
                legal_record TEXT,
                validation_summary TEXT,
                design_brief TEXT,
                content_plan TEXT,
                svg_filename TEXT,
                png_filename TEXT,
                artwork_filename TEXT,
                warnings TEXT,
                logs TEXT
            )
        """)
        conn.commit()

    columns = {
        row["name"]
        for row in get_connection().execute("PRAGMA table_info(infographic_jobs)").fetchall()
    }
    if "design_brief" not in columns:
        with get_connection() as conn:
            conn.execute("ALTER TABLE infographic_jobs ADD COLUMN design_brief TEXT")
            conn.commit()
            logger.info("Added design_brief column to existing job archive")

    logger.info("Database initialized successfully at %s", settings.sqlite_db_path)

def create_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    job_id = job_data["job_id"]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO infographic_jobs (
                job_id, status, current_stage, progress_percent,
                article_name, article_url, pdf_url, language,
                output_format, enable_image_generation, width, height,
                created_at, updated_at, error_message,
                source_metadata, legal_record, validation_summary,
                design_brief, content_plan, svg_filename, png_filename,
                artwork_filename, warnings, logs
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?
            )
        """, (
            job_id,
            job_data.get("status", "idle"),
            job_data.get("current_stage", 0),
            job_data.get("progress_percent", 0),
            job_data.get("article_name"),
            job_data.get("article_url"),
            job_data.get("pdf_url"),
            job_data.get("language", "en"),
            job_data.get("output_format", "both"),
            1 if job_data.get("enable_image_generation") else 0,
            job_data.get("width", 1200),
            job_data.get("height", 1200),
            now,
            now,
            job_data.get("error_message"),
            json.dumps(job_data.get("source_metadata")) if job_data.get("source_metadata") else None,
            json.dumps(job_data.get("legal_record")) if job_data.get("legal_record") else None,
            json.dumps(job_data.get("validation_summary")) if job_data.get("validation_summary") else None,
            json.dumps(job_data.get("design_brief")) if job_data.get("design_brief") else None,
            json.dumps(job_data.get("content_plan")) if job_data.get("content_plan") else None,
            job_data.get("svg_filename"),
            job_data.get("png_filename"),
            job_data.get("artwork_filename"),
            json.dumps(job_data.get("warnings", [])),
            json.dumps(job_data.get("logs", []))
        ))
        conn.commit()
    return get_job(job_id)

def update_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now
    
    fields = []
    values = []
    
    json_fields = ["source_metadata", "legal_record", "validation_summary", "design_brief", "content_plan", "warnings", "logs"]
    
    for k, v in updates.items():
        if k in json_fields and v is not None and not isinstance(v, str):
            fields.append(f"{k} = ?")
            values.append(json.dumps(v))
        elif k == "enable_image_generation":
            fields.append(f"{k} = ?")
            values.append(1 if v else 0)
        else:
            fields.append(f"{k} = ?")
            values.append(v)
            
    values.append(job_id)
    query = f"UPDATE infographic_jobs SET {', '.join(fields)} WHERE job_id = ?"
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()
        
    return get_job(job_id)

_JSON_LIST_FIELDS = {"warnings", "logs"}

def _decode_job_row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for field in ["source_metadata", "legal_record", "validation_summary", "design_brief", "content_plan", "warnings", "logs"]:
        raw = d.get(field)
        if raw:
            try:
                d[field] = json.loads(raw)
            except Exception:
                d[field] = [] if field in _JSON_LIST_FIELDS else None
        else:
            d[field] = [] if field in _JSON_LIST_FIELDS else None
    d["enable_image_generation"] = bool(d.get("enable_image_generation", 0))
    return d

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM infographic_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return _decode_job_row(row) if row is not None else None

def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM infographic_jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_decode_job_row(row) for row in cursor.fetchall()]

def delete_job(job_id: str) -> bool:
    job = get_job(job_id)
    if not job:
        return False
    
    # Remove files if they exist
    storage_dir = Path(settings.storage_dir)
    for fname in [job.get("svg_filename"), job.get("png_filename"), job.get("artwork_filename")]:
        if fname:
            fpath = storage_dir / fname
            if fpath.exists() and fpath.is_file():
                try:
                    fpath.unlink()
                except Exception as e:
                    logger.warning("Failed to delete file %s: %s", fpath, e)
                    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM infographic_jobs WHERE job_id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0
