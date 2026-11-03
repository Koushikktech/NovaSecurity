import json

import pytest
from fastapi.testclient import TestClient

from api import app
from config import settings
from persistence.database import init_database
from providers.codex_cli import CodexCLIProvider
from schemas.provider import ProviderResponse


def test_provider_model_validation_and_local_policy(monkeypatch):
    client = TestClient(app)
    body = {"repo_url": "https://github.com/example/app", "provider": "codex_cli", "model": "gemini-test"}
    assert client.post("/api/v1/reviews", json=body).status_code == 422
    body["model"] = "gpt-test"
    monkeypatch.setattr(settings, "codex_cli_enabled", False)
    assert client.post("/api/v1/reviews", json=body).status_code == 403
    monkeypatch.setattr(settings, "codex_cli_enabled", True)
    monkeypatch.setenv("PROOFLINE_OPERATOR_TOKEN", "test-only")
    remote = TestClient(app, client=("203.0.113.1", 4567))
    response = remote.post("/api/v1/reviews", json=body, headers={"Authorization": "Bearer test-only"})
    assert response.status_code == 403 and "localhost" in response.json()["detail"]


def test_codex_uses_existing_harness_and_configuration_survives_resume_and_repair(tmp_path, monkeypatch):
    import routes.v1 as routes
    from review.harness import InvestigationStep
    from schemas.provider import ChallengeResult, PatchProposalResult, ReviewCandidatesResult

    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "reviews.db"))
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspaces")
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    monkeypatch.setattr(settings, "codex_cli_enabled", True)
    init_database()
    observed = []

    class StubCodex(CodexCLIProvider):
        def __init__(self, **kwargs):
            super().__init__(default_model="gpt-test", **kwargs)

        def is_available(self):
            return True

        def generate_structured(self, request, schema):
            observed.append((request.stage, self._select_model(request.model_role), self.thinking))
            if schema is InvestigationStep:
                data = schema(ready=True, tools=[])
            elif schema is ReviewCandidatesResult:
                data = schema(findings=[], review_summary="Controlled provider integration")
            elif schema is ChallengeResult:
                claims = json.loads(request.context.split("CLAIMS:\n")[1].split("\nSOURCE:\n")[0])
                data = schema(
                    assessments=[
                        {
                            **{key: row[key] for key in ("rule_id", "path", "start_line")},
                            "is_valid": True,
                            "confidence_assessment": "confirmed",
                            "evidence_status": "source_supported",
                            "explanation": "Default object is shared across calls",
                            "citations": [{"path": "app.py", "start_line": 1, "quote": "def collect(item, items=[]):"}],
                        }
                        for row in claims
                    ]
                )
            elif schema is PatchProposalResult:
                data = schema(summary="Proposed fix", rationale="Avoid shared state", edits=[])
            else:
                pytest.fail(str(schema))
            return ProviderResponse(success=True, data=data, model_id=self._select_model(request.model_role))

    monkeypatch.setattr(routes, "CodexCLIProvider", StubCodex)
    payload = {
        "provider": "codex_cli",
        "model": "gpt-review",
        "role_models": {"verify_reasoning": "gpt-verifier", "patch": "gpt-repair"},
        "codex_reasoning": "xhigh",
        "files": [
            {"path": "app.py", "content": "def collect(item, items=[]):\n    items.append(item)\n    return items\n"}
        ],
    }
    client = TestClient(app)
    created = client.post("/api/v1/reviews/folder", json=payload)
    assert created.status_code == 202, created.text
    identifier = created.json()["run_id"]
    run = client.get("/api/v1/reviews/" + identifier).json()
    assert run["provider"] == "codex_cli" and run["status"] == "completed", run.get("errors")
    assert run["coverage"]["run_config"]["provider"] == "codex_cli"
    assert run["coverage"]["run_config"]["codex_reasoning"] == "xhigh"
    assert run["coverage"]["investigation"]["model_calls"] >= 3
    assert any(stage.startswith("investigate_") for stage, _, _ in observed)
    assert any(model == "gpt-verifier" and effort == "xhigh" for _, model, effort in observed)
    resumed = client.post(f"/api/v1/reviews/{identifier}/resume")
    assert resumed.status_code == 202, resumed.text
    restored = client.get("/api/v1/reviews/" + resumed.json()["run_id"]).json()
    assert restored["coverage"]["run_config"] == run["coverage"]["run_config"]
    findings = client.get(f"/api/v1/reviews/{identifier}/findings").json()
    assert findings
    proposal = client.post(f"/api/v1/findings/{findings[0]['id']}/patches")
    assert proposal.status_code == 400  # empty fake edit proposal is not accepted
    assert observed[-1] == ("patch", "gpt-repair", "xhigh")
