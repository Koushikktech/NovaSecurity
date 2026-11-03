from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    import api as legacy_api
    import routes.v1 as routes
    from providers.fake import FakeLLMProvider
    monkeypatch.setattr(legacy_api, "GeminiProvider", FakeLLMProvider)
    monkeypatch.setattr(routes, "GeminiProvider", FakeLLMProvider)
    monkeypatch.setattr(routes, "UnavailableProvider", FakeLLMProvider)

from api import app

client = TestClient(app)


def test_healthz_and_readyz():
    res_h = client.get("/healthz")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "ok"

    res_r = client.get("/readyz")
    assert res_r.status_code == 200
    assert res_r.json()["status"] == "ready"


def test_capabilities_endpoint():
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert data["product"] == "Proofline"
    assert "python" in data["languages"]
    assert "ruff" in data["analyzers"]
    assert "bandit" in data["analyzers"]
    assert "gemini" in data["analyzers"]


def test_list_recorded_examples():
    res = client.get("/api/v1/examples")
    assert res.status_code == 200
    examples = res.json()
    assert len(examples) >= 3
    ids = [e["id"] for e in examples]
    assert "example-expense-service" in ids
    assert "example-lets-be-bad-guys" in ids
    assert "example-vulpy" in ids


def test_review_create_and_query():
    from pathlib import Path
    demo_dir = str(Path(__file__).resolve().parents[2] / "fixtures" / "demo-api")
    req_payload = {
        "repo_url": "https://github.com/proofline/demo-api",
        "local_dir": demo_dir,
    }
    create_res = client.post("/api/v1/reviews", json=req_payload)
    assert create_res.status_code == 202
    run_id = create_res.json()["run_id"]
    assert run_id is not None

    # Poll review status
    import time
    for _ in range(20):
        get_res = client.get(f"/api/v1/reviews/{run_id}")
        assert get_res.status_code == 200
        run_data = get_res.json()
        if run_data["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    assert run_data["status"] == "completed"

    # Query findings
    findings_res = client.get(f"/api/v1/reviews/{run_id}/findings")
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert len(findings) > 0

    # Test disposition update
    target_finding = findings[0]
    finding_id = target_finding["id"]

    disp_res = client.patch(
        f"/api/v1/findings/{finding_id}/disposition",
        json={"disposition": "accepted", "reason": "Acknowledged issue by developer"},
    )
    assert disp_res.status_code == 200
    assert disp_res.json()["disposition"] == "accepted"

    # Test export (json & markdown)
    exp_json = client.get(f"/api/v1/reviews/{run_id}/export?format=json")
    assert exp_json.status_code == 200
    assert "findings" in exp_json.json()

    exp_md = client.get(f"/api/v1/reviews/{run_id}/export?format=markdown")
    assert exp_md.status_code == 200
    assert "Proofline Review Report" in exp_md.json()["markdown"]

    # Test evidence retrieval
    ev_res = client.get(f"/api/v1/reviews/{run_id}/evidence/0")
    assert ev_res.status_code == 200
    assert "tool_or_profile" in ev_res.json()

    # Test publish review
    pub_rev = client.post(f"/api/v1/reviews/{run_id}/publish")
    assert pub_rev.status_code == 200
    assert "published" in pub_rev.json()

    # Test generate patch and publish patch
    patch_gen = client.post(f"/api/v1/findings/{finding_id}/patches")
    if patch_gen.status_code == 200:
        patch_id = patch_gen.json()["id"]
        pub_patch = client.post(f"/api/v1/patches/{patch_id}/publish")
        assert pub_patch.status_code == 200
        assert "published" in pub_patch.json()


def test_hero_demo_scan_and_fix():
    # Test POST /api/demo with expense-service
    demo_res = client.post("/api/demo", json={"repo_key": "expense-service"})
    assert demo_res.status_code == 200
    scan_id = demo_res.json()["scan_id"]
    assert scan_id is not None

    # Poll scan status
    import time
    for _ in range(20):
        s_res = client.get(f"/api/scan/{scan_id}")
        assert s_res.status_code == 200
        if s_res.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    scan_data = s_res.json()
    assert scan_data["status"] == "completed"
    assert scan_data["summary"]["total"] >= 1

    # Test get findings and graph
    f_res = client.get(f"/api/scan/{scan_id}/findings")
    assert f_res.status_code == 200
    findings = f_res.json()["findings"]
    assert len(findings) >= 1

    g_res = client.get(f"/api/scan/{scan_id}/graph")
    assert g_res.status_code == 200
    assert "nodes" in g_res.json()

    # Test start fix
    fix_res = client.post(f"/api/scan/{scan_id}/fix", json={"finding_index": 0})
    assert fix_res.status_code == 200
    fix_id = fix_res.json()["fix_id"]

    for _ in range(20):
        fix_status = client.get(f"/api/fix/{fix_id}")
        assert fix_status.status_code == 200
        if fix_status.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    fix_data = fix_status.json()
    assert fix_data["status"] in ("completed", "failed")
    if fix_data["status"] == "completed":
        assert fix_data["diff"]
    else:
        assert fix_data.get("error")  # Unsafe or unrelated canned edits must fail closed.

    # Test pull request creation
    pr_res = client.post(f"/api/fix/{fix_id}/pull-request")
    assert pr_res.status_code == (200 if fix_data["status"] == "completed" else 409)
    if pr_res.status_code == 200:
        assert pr_res.json()["pr"]["status"] in ("compare_ready", "created")
