from providers.base import BaseLLMProvider
from schemas.provider import ProviderResponse


class UnavailableProvider(BaseLLMProvider):
    def is_available(self):
        return False

    def generate_structured(self, request, response_schema):
        return ProviderResponse(
            success=False,
            model_id="unavailable",
            error="Configure GEMINI_API_KEY and a supported model for contextual review; static results remain available",
        )
