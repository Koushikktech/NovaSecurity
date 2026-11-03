from __future__ import annotations

from pydantic import BaseModel, Field


class VerificationProfile(BaseModel):
    container_command: list[str] | None = Field(default=None, min_length=1, max_length=40)
    runtime: str = "python"
    image_env: str = "PROOFLINE_VERIFICATION_IMAGE"
    require_base: bool = False
    profile_id: str
    name: str
    description: str
    test_command: list[str]
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    regression_test_id: str
    happy_path_test_id: str
    environment_vars: dict[str, str] = Field(default_factory=dict)
    oracle_dir: str = "fixtures/demo-api/tests"
    oracle_file: str = "test_expense_search.py"


# Registry of trusted verification profiles (profiles live outside scanned PR contents)
TRUSTED_PROFILES: dict[str, VerificationProfile] = {
    "expense_service_sql": VerificationProfile(
        profile_id="expense_service_sql",
        name="Expense Service SQL Injection Oracle",
        description="Verifies SQL injection remediation in expense search service while ensuring valid searches pass.",
        test_command=[".venv/bin/pytest", "-v", "tests/test_expense_search.py"],
        timeout_seconds=20,
        regression_test_id="test_unauthorized_expense_leak",
        happy_path_test_id="test_normal_expense_search",
    ),
}


TRUSTED_PROFILES["python_contract"] = VerificationProfile(
    profile_id="python_contract",
    name="Python contract regression",
    description="Base/head/patched behavioral regression",
    test_command=[],
    regression_test_id="test_regression",
    happy_path_test_id="test_happy",
    oracle_dir="fixtures/contract-oracles/python",
    oracle_file="test_contract.py",
    require_base=True,
)
TRUSTED_PROFILES["javascript_contract"] = VerificationProfile(
    profile_id="javascript_contract",
    name="JavaScript contract regression",
    description="Node execution of JavaScript output (including compiled TypeScript)",
    test_command=[],
    regression_test_id="test_regression",
    happy_path_test_id="test_happy",
    oracle_dir="fixtures/contract-oracles/javascript",
    oracle_file="contract.test.cjs",
    require_base=True,
    runtime="node",
    image_env="PROOFLINE_NODE_VERIFICATION_IMAGE",
)


TRUSTED_PROFILES["checkout_contract"] = VerificationProfile(
    profile_id="checkout_contract",
    name="Checkout without a coupon",
    description="The same checkout regression and explicit-discount happy path on base, changed and repaired code.",
    test_command=[],
    regression_test_id="test_checkout_without_coupon",
    happy_path_test_id="test_explicit_discount",
    oracle_dir="fixtures/flagship/oracle",
    oracle_file="test_checkout.py",
    require_base=True,
)


def get_profile(profile_id: str) -> VerificationProfile | None:
    return TRUSTED_PROFILES.get(profile_id)


TRUSTED_PROFILES["typescript_contract"] = VerificationProfile(
    profile_id="typescript_contract",
    name="TypeScript contract regression",
    description="Trusted TypeScript transpilation and Node execution; not full project type checking",
    test_command=[],
    regression_test_id="test_regression",
    happy_path_test_id="test_happy",
    oracle_dir="fixtures/contract-oracles/typescript",
    oracle_file="contract.test.cjs",
    require_base=True,
    runtime="node",
    image_env="PROOFLINE_NODE_VERIFICATION_IMAGE",
)


def load_operator_profiles():
    import json
    import os
    from pathlib import Path

    from config import settings

    value = os.getenv("PROOFLINE_VERIFICATION_PROFILES", "")
    if not value:
        return
    source = Path(value).resolve()
    if source.is_relative_to(settings.workspace_dir.resolve()) or source.stat().st_size > 200000:
        raise ValueError("Verification profiles must be operator-owned, outside review workspaces and under 200 KB")
    for record in json.loads(source.read_text()):
        profile = VerificationProfile.model_validate(record)
        if profile.profile_id in TRUSTED_PROFILES:
            raise ValueError("Operator profile cannot shadow a built-in profile")
        if profile.runtime not in {"python", "node"}:
            raise ValueError("Unsupported verification runtime")
        TRUSTED_PROFILES[profile.profile_id] = profile


load_operator_profiles()
