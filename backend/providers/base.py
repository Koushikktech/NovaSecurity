from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from schemas.provider import ProviderResponse, StructuredGenerationRequest

T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self,
        request: StructuredGenerationRequest,
        response_schema: type[T],
    ) -> ProviderResponse[T]:
        """Generate structured data conforming to response_schema."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and available."""
        pass
