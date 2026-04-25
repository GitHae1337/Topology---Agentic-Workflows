from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class LLMMessage(BaseModel):
    """A message in the conversation."""
    role: str  # "system", "user", "assistant"
    content: str


class LLMResponse(BaseModel):
    """Response from an LLM."""
    content: str
    model: str
    usage: Optional[dict] = None


class LLMService(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass


class LLMServiceFactory:
    """Factory for creating LLM services (OpenAI only)."""

    _openai_service = None

    @classmethod
    def get_service(cls, model: str) -> LLMService:
        """Get the OpenAI LLM service for any model."""
        return cls._get_openai_service()

    @classmethod
    def _get_openai_service(cls) -> LLMService:
        if cls._openai_service is None:
            from .providers.openai_provider import OpenAIService
            cls._openai_service = OpenAIService()
        return cls._openai_service
