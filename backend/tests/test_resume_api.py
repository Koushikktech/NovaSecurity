from fastapi.testclient import TestClient

from api import app
from config import settings
from persistence.database import init_database


def test_resume_uses_sealed_source_even_if_original_upload_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspaces")
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "reviews.db"))
    monkeypatch.setattr(settings, "gemini_api_key", "")
    init_database()
    client = TestClient(app)
    original = "def total(items):\n    return sum(items)\n"
    created = client.post("/api/v1/reviews/folder", json={"files": [{"path": "app.py", "content": original}]})
    assert created.status_code == 202, created.text
    first = created.json()["run_id"]
    upload = settings.workspace_dir / (first + "-upload") / "app.py"
    upload.write_text('raise RuntimeError("changed after review")')
    resumed = client.post("/api/v1/reviews/" + first + "/resume")
    assert resumed.status_code == 202, resumed.text
    second = resumed.json()["run_id"]
    source = client.get("/api/v1/reviews/" + second + "/source", params={"path": "app.py"})
    assert source.status_code == 200 and source.json()["content"] == original
    report = client.get("/api/v1/reviews/" + second).json()
    assert report["coverage"]["resumed_from"] == first
