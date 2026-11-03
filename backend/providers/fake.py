from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from schemas.provider import (
    ChallengeResult,
    PatchProposalResult,
    ProviderResponse,
    ProviderUsage,
    ReviewCandidatesResult,
    StructuredGenerationRequest,
)

from .base import BaseLLMProvider

T = TypeVar("T", bound=BaseModel)


class FakeLLMProvider(BaseLLMProvider):
    def __init__(self, canned_responses: dict[str, Any] | None = None):
        self.canned_responses = canned_responses or {}
        self.call_history: list[StructuredGenerationRequest] = []
        self.simulate_error: str | None = None
        self.simulate_timeout: bool = False

    def is_available(self) -> bool:
        return True

    def register_response(self, stage: str, data: Any) -> None:
        self.canned_responses[stage] = data

    def generate_structured(
        self,
        request: StructuredGenerationRequest,
        response_schema: type[T],
    ) -> ProviderResponse[T]:
        self.call_history.append(request)

        if self.simulate_timeout:
            return ProviderResponse[T](
                success=False,
                model_id="fake-gemini",
                error="Timeout exceeded",
                duration_ms=45000,
            )

        if self.simulate_error:
            return ProviderResponse[T](
                success=False,
                model_id="fake-gemini",
                error=self.simulate_error,
                duration_ms=10,
            )

        # Check if registered for stage
        if request.stage in self.canned_responses:
            raw_data = self.canned_responses[request.stage]
            if isinstance(raw_data, response_schema):
                validated = raw_data
            elif isinstance(raw_data, dict):
                validated = response_schema.model_validate(raw_data)
            else:
                validated = raw_data
            return ProviderResponse[T](
                success=True,
                data=validated,
                raw_text=json.dumps(validated.model_dump() if hasattr(validated, "model_dump") else {}),
                model_id="fake-gemini",
                duration_ms=25,
                usage=ProviderUsage(prompt_tokens=150, candidate_tokens=80, total_tokens=230),
            )

        # Generate sensible default mock based on response_schema
        if response_schema == ReviewCandidatesResult:
            mock_res = ReviewCandidatesResult(
                findings=[],
                review_summary="Clean review: no suspicious data flows or severe bugs detected in diff.",
            )
            return ProviderResponse[T](
                success=True,
                data=mock_res,  # type: ignore
                raw_text=mock_res.model_dump_json(),
                model_id="fake-gemini",
                duration_ms=20,
                usage=ProviderUsage(prompt_tokens=200, candidate_tokens=50, total_tokens=250),
            )
        elif response_schema == ChallengeResult:
            import re

            claims = []
            # Test provider explicitly marks claims unresolved rather than inventing evidence.
            match = re.search(r"CLAIMS:\n(.*?)\nSOURCE:", request.context, re.S)
            if match:
                claims = json.loads(match.group(1))
            mock_res = ChallengeResult(
                assessments=[
                    {
                        "rule_id": c["rule_id"],
                        "path": c["path"],
                        "start_line": c["start_line"],
                        "is_valid": False,
                        "confidence_assessment": "needs_review",
                        "explanation": "Offline test provider cannot establish source evidence",
                        "evidence_status": "insufficient_evidence",
                    }
                    for c in claims
                ]
            )
            return ProviderResponse[T](
                success=True,
                data=mock_res,  # type: ignore
                raw_text=mock_res.model_dump_json(),
                model_id="fake-gemini",
                duration_ms=15,
                usage=ProviderUsage(prompt_tokens=100, candidate_tokens=25, total_tokens=125),
            )
        elif response_schema == PatchProposalResult:
            mock_res = PatchProposalResult(
                edits=[],
                summary="No patch needed.",
                rationale="No edits required.",
                tests_to_run=[],
            )
            return ProviderResponse[T](
                success=True,
                data=mock_res,  # type: ignore
                raw_text=mock_res.model_dump_json(),
                model_id="fake-gemini",
                duration_ms=30,
                usage=ProviderUsage(prompt_tokens=180, candidate_tokens=60, total_tokens=240),
            )

        return ProviderResponse[T](
            success=False,
            model_id="fake-gemini",
            error=f"No mock response available for schema {response_schema}",
        )
