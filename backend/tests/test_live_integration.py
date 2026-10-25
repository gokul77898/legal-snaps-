"""
Real end-to-end integration test: two genuinely different legal articles, live web
search, live retrieval, live Qwen analysis through Hugging Face, live artifacts.

    RUN_LIVE_TESTS=1 ./.venv/bin/python -m pytest tests/test_live_integration.py -v -s

Skipped by default so the offline suite never depends on the network or on API credits.
If Hugging Face rejects the request, the job MUST fail with that error - never "completed".
"""
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Live integration test. Set RUN_LIVE_TESTS=1 to run (needs network + a Hugging Face token with inference credits).",
)

ARTICLES = [
    "Sukanya Shantha v. Union of India 2024 caste discrimination in prisons",
    "Justice K.S. Puttaswamy Retd v. Union of India 2017 right to privacy",
]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def run_article(client: TestClient, topic: str) -> dict:
    created = client.post("/api/v1/infographics", json={
        "article_name": topic,
        "enable_image_generation": False,
        "output_format": "both",
    })
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]

    # Starlette executes background tasks during the request in TestClient, so the job
    # has already reached a terminal state by the time we poll.
    job = client.get(f"/api/v1/infographics/{job_id}").json()
    print(f"\n--- {topic}\nstatus={job['status']} stage={job['current_stage']}")
    for line in job["logs"][-6:]:
        print("  ", line)
    if job["warnings"]:
        print("   warnings:", job["warnings"][:3])
    return job


def test_two_articles_end_to_end(client):
    jobs = [run_article(client, topic) for topic in ARTICLES]

    for job, topic in zip(jobs, ARTICLES):
        assert job["status"] in ("completed", "failed"), job["status"]
        assert job["source_metadata"] is not None, f"No source was retrieved for {topic}"
        assert job["source_metadata"]["url"], "Source URL was not recorded"

    # Honest failure is acceptable; silent success is not.
    failed = [j for j in jobs if j["status"] == "failed"]
    if failed:
        for job in failed:
            assert job["error_message"], "Job failed without an error message"
            assert not job["error_message"].startswith("Hugging Face legal analysis failed: None")
            print("\nBLOCKED: Hugging Face rejected the request ->", job["error_message"][:200])
        pytest.skip(f"Hugging Face unavailable: {failed[0]['error_message'][:160]}")

    first, second = jobs
    assert first["job_id"] != second["job_id"]

    # Distinct sources and distinct legal analysis.
    assert first["source_metadata"]["url"] != second["source_metadata"]["url"]
    assert first["legal_record"]["case_name"] != second["legal_record"]["case_name"]

    first_headline = (first["content_plan"]["headline"] or "").lower()
    second_headline = (second["content_plan"]["headline"] or "").lower()
    assert first_headline != second_headline
    assert "sukanya" in first_headline
    assert "puttaswamy" in second_headline

    # Artifacts belong to their own job and contain their own content.
    storage = Path(settings.storage_dir)
    for job, expected in zip(jobs, ("sukanya", "puttaswamy")):
        assert job["has_svg"] and job["has_png"]
        svg_path = storage / job["svg_filename"]
        png_path = storage / job["png_filename"]
        assert job["svg_filename"].startswith(job["job_id"])
        assert job["png_filename"].startswith(job["job_id"])

        svg_text = svg_path.read_text(encoding="utf-8")
        assert expected in svg_text.lower()
        assert png_path.read_bytes().startswith(PNG_MAGIC)
        assert png_path.stat().st_size > 8192

    assert "sukanya" not in (storage / second["svg_filename"]).read_text(encoding="utf-8").lower()


def test_recorded_source_matches_the_database(client):
    job = run_article(client, ARTICLES[1])
    if job["status"] == "failed":
        pytest.skip("Hugging Face unavailable; persistence of failed jobs is asserted elsewhere")

    with sqlite3.connect(settings.sqlite_db_path) as conn:
        row = conn.execute(
            "SELECT status, source_metadata FROM infographic_jobs WHERE job_id = ?",
            (job["job_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == job["status"]
    assert job["source_metadata"]["url"] in row[1]
