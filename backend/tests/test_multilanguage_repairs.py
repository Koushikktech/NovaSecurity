import pytest

from providers.fake import FakeLLMProvider
from remediation.patcher import Patcher
from schemas.contracts import Finding, FindingCategory, Location, Severity
from schemas.provider import PatchFileEdit, PatchProposalResult


@pytest.mark.parametrize("suffix", ["js", "jsx", "ts", "tsx"])
def test_repair_rejects_invalid_syntax_without_executing_javascript(tmp_path, suffix):
    source = "export function total(items) { return items.length; }\n"
    path = f"app.{suffix}"
    (tmp_path / path).write_text(source)
    provider = FakeLLMProvider()
    provider.register_response(
        "patch",
        PatchProposalResult(
            edits=[
                PatchFileEdit(
                    path=path, old_content="return items.length;", replacement="return ( ;", rationale="invalid"
                )
            ],
            summary="bad patch",
            rationale="test",
        ),
    )
    finding = Finding(
        run_id="syntax",
        stable_fingerprint="test",
        category=FindingCategory.BUG,
        rule_id="test:empty",
        title="Example finding",
        explanation="Check empty input",
        user_impact="Failure",
        severity=Severity.MEDIUM,
        primary_location=Location(path=path, start_line=1, end_line=1),
    )
    result = Patcher(provider).propose_patch(finding, tmp_path)
    assert not result.success and "invalid JavaScript/TypeScript syntax" in result.error
    assert (tmp_path / path).read_text() == source


def test_typescript_repair_is_language_appropriate_and_only_proposed(tmp_path):
    source = "export const total = (items: number[]): number => items[0];\n"
    (tmp_path / "app.ts").write_text(source)

    class RecordingProvider(FakeLLMProvider):
        def generate_structured(self, request, schema):
            assert "```typescript" in request.context
            assert "Review Finding:" in request.context and "Vulnerability Title:" not in request.context
            assert "Category: bug" in request.context
            return super().generate_structured(request, schema)

    provider = RecordingProvider()
    provider.register_response(
        "patch",
        PatchProposalResult(
            edits=[
                PatchFileEdit(
                    path="app.ts", old_content="items[0]", replacement="items[0] ?? 0", rationale="Handle empty input"
                )
            ],
            summary="Handle empty input",
            rationale="Preserve number return type",
        ),
    )
    finding = Finding(
        run_id="syntax",
        stable_fingerprint="test",
        category=FindingCategory.BUG,
        rule_id="test:empty",
        title="Empty input returns undefined",
        explanation="Caller requires a number",
        user_impact="NaN downstream",
        severity=Severity.MEDIUM,
        primary_location=Location(path="app.ts", start_line=1, end_line=1),
    )
    result = Patcher(provider).propose_patch(finding, tmp_path)
    assert result.success and result.patch.status.value == "proposed"
    assert not result.patch.checks
    assert (tmp_path / "app.ts").read_text() == source
