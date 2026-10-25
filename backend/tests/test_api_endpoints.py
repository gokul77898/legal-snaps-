import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_db()

client = TestClient(app)

def test_health_check_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "Legal Snaps Infographic Generator"
    assert "renderer_available" in data
    assert "storage_writable" in data

def test_create_infographic_empty_input_fails():
    resp = client.post("/api/v1/infographics", json={})
    assert resp.status_code == 400
    assert "must supply an article name" in resp.json()["detail"]

def test_create_infographic_valid_job():
    payload = {
        "article_name": "Donoghue v Stevenson",
        "output_format": "both",
        "enable_image_generation": False,
        "width": 1200,
        "height": 1200
    }
    resp = client.post("/api/v1/infographics", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["article_name"] == "Donoghue v Stevenson"
    assert data["status"] in ("idle", "searching", "retrieving", "completed")

    # Poll status endpoint
    job_id = data["job_id"]
    get_resp = client.get(f"/api/v1/infographics/{job_id}")
    assert get_resp.status_code == 200
    job_data = get_resp.json()
    assert job_data["job_id"] == job_id

def test_list_infographics():
    resp = client.get("/api/v1/infographics?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_get_nonexistent_job():
    resp = client.get("/api/v1/infographics/nonexistent-id-12345")
    assert resp.status_code == 404
