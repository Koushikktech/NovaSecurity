import pytest

from analysis.languages import javascript_analysis, python_contracts, select_context
from providers.unavailable import UnavailableProvider
from review.orchestrator import ReviewOrchestrator
from verification.runner import parse_junit


def file(path, content):
    return {"relative_path": path, "content": content, "lines": len(content.splitlines())}


def test_javascript_real_parser_and_safe_controls():
    files = [
        file(
            "service.ts",
            "export const save = async (items: string[]) => { items.forEach(async x => { await fetch(x); }); };",
        ),
        file("safe.ts", "export async function save(items: string[]) { for (const x of items) await fetch(x); }"),
        file("view.tsx", "export const V = () => <div>Hello</div>;"),
    ]
    findings, index, coverage = javascript_analysis(files, "test")
    assert coverage["status"] == "executed"
    assert [(f.primary_location.path, f.rule_id) for f in findings] == [("service.ts", "js:async-foreach")]
    assert index["service.ts"]["symbols"][0]["name"] == "save"


def test_python_signature_alias_and_safe_keyword():
    base = [file("service.py", "def load(page):\n    return page\n")]
    head = [
        file("service.py", "def load(page, size):\n    return page\n"),
        file("caller.py", "from service import load as get\nget(1)\nget(1, size=2)\n"),
    ]
    result = python_contracts(base, head, {"service.py"}, "run")
    assert len(result) == 1 and result[0].primary_location.path == "caller.py"
    assert result[0].related_locations[0].path == "service.py"


def test_context_includes_reverse_dependency():
    files = [
        file("service.py", "def load(): pass"),
        file("caller.py", "from service import load"),
        file("unrelated.py", "x=1"),
    ]
    text, coverage = select_context(files, {"service.py"})
    assert "caller.py" in text and "unrelated.py" not in text


def test_junit_distinguishes_infrastructure_and_assertion():
    assert (
        parse_junit(
            '<testsuite><testcase name="x"><failure type="AssertionError">assert 1 == 2</failure></testcase></testsuite>'
        )["x"]
        == "assertion_failure"
    )
    assert (
        parse_junit('<testsuite><testcase name="x"><error>ImportError</error></testcase></testsuite>')["x"] == "error"
    )
    with pytest.raises(ValueError):
        parse_junit("<testsuite/>")


def test_model_unavailable_is_partial_real_pipeline(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    run, findings = ReviewOrchestrator(provider=UnavailableProvider()).execute_review("local", local_dir=str(tmp_path))
    assert run.status.value == "partial"
    assert run.stage_statuses["gemini_review"].value == "failed"
    assert run.provider == "UnavailableProvider"


def test_patcher_rejects_ambiguous_and_other_files():
    from remediation.patcher import apply_edits_to_text
    from schemas.contracts import FileEdit

    _, error = apply_edits_to_text("x+x", [FileEdit(path="a.py", old_content="x", replacement="y", rationale="")])
    assert error


def test_verifier_uses_isolated_copy_and_preserves_source(tmp_path, monkeypatch):
    import verification.runner as module
    from config import settings
    from schemas.contracts import FileEdit, Patch
    from verification.runner import VerificationRunner

    monkeypatch.setattr(settings, "execution_enabled", True)
    monkeypatch.setattr(module.shutil, "which", lambda _: "/docker")
    monkeypatch.setenv("PROOFLINE_VERIFICATION_IMAGE", "example@sha256:" + "a" * 64)
    (tmp_path / "app.py").write_text("value = 1\n")
    patch = Patch(
        finding_id="f", run_id="r", edits=[FileEdit(path="app.py", old_content="1", replacement="2", rationale="")]
    )

    def execute(self, work, profile, phase, patch):
        assert work != tmp_path
        assert (work / "app.py").read_text() == ("value = 1\n" if phase == "before" else "value = 2\n")
        return (
            (1, {profile.regression_test_id: "assertion_failure", profile.happy_path_test_id: "passed"})
            if phase == "before"
            else (0, {profile.regression_test_id: "passed", profile.happy_path_test_id: "passed"})
        )

    monkeypatch.setattr(VerificationRunner, "_execute", execute)
    assert VerificationRunner(tmp_path).verify_patch(patch, "expense_service_sql")[0]
    assert (tmp_path / "app.py").read_text() == "value = 1\n"


def test_operator_access_boundary(monkeypatch):
    from fastapi.testclient import TestClient

    from api import app

    monkeypatch.setenv("PROOFLINE_OPERATOR_TOKEN", "test-operator")
    client = TestClient(app)
    assert client.get("/api/v1/capabilities").status_code == 401
    assert client.get("/api/v1/capabilities", headers={"Authorization": "Bearer test-operator"}).status_code == 200


def test_typescript_signature_compatibility():
    from analysis.languages import javascript_contracts

    _, base, _ = javascript_analysis([file("service.ts", "export function load(page: number) { return page; }")], "r")
    _, head, _ = javascript_analysis(
        [
            file("service.ts", "export function load(page: number, size: number) { return page; }"),
            file("caller.ts", "import { load as get } from './service';\nget(1);\nget(1, 20);"),
        ],
        "r",
    )
    findings = javascript_contracts(base, head, {"service.ts"}, "r")
    assert len(findings) == 1 and findings[0].primary_location.start_line == 2


def test_controlled_reviewer_example_real_base_head(monkeypatch):
    from fastapi.testclient import TestClient

    import routes.v1 as routes
    from api import app

    monkeypatch.setattr(routes, "GeminiProvider", UnavailableProvider)
    client = TestClient(app)
    created = client.post("/api/v1/examples/reviewer")
    assert created.status_code == 202, created.text
    run_id = created.json()["run_id"]
    run = client.get("/api/v1/reviews/" + run_id).json()
    assert run["base_sha"] and run["head_sha"] and run["base_sha"] != run["head_sha"]
    findings = client.get("/api/v1/reviews/" + run_id + "/findings").json()
    rules = {f["rule_id"] for f in findings}
    assert "python:changed-signature" in rules and "js:async-foreach" in rules


def test_explicit_static_mode_never_calls_provider(tmp_path):
    class ForbiddenProvider(UnavailableProvider):
        def generate_structured(self, *args):
            raise AssertionError("Static mode must not call a model")

    (tmp_path / "app.py").write_text("value = 1\n")
    run, _ = ReviewOrchestrator(provider=ForbiddenProvider()).execute_review(
        "local", local_dir=str(tmp_path), static_only=True
    )
    assert run.status.value == "completed"
    assert run.stage_statuses["gemini_review"].value == "skipped"
