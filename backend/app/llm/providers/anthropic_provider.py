import os
from typing import List
import logging
from anthropic import AsyncAnthropic

from ..base import LLMService, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicService(LLMService):
    """Anthropic LLM service implementation."""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set - Anthropic calls will fail")
        self.client = AsyncAnthropic(api_key=api_key) if api_key else None

    async def generate(
        self,
        messages: List[LLMMessage],
        model: str = "claude-3-opus-20240229",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response using Anthropic API."""
        if not self.client:
            logger.error("Anthropic client not initialized - missing API key")
            return LLMResponse(
                content="[Error: Anthropic API key not configured]",
                model=model,
            )

        logger.info(f"Anthropic generate: model={model}, messages={len(messages)}")

        # Extract system message if present
        system_content = ""
        conversation_messages = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        # Map model names to Anthropic model IDs
        model_map = {
            "claude-3-opus": "claude-3-opus-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude-3-haiku": "claude-3-haiku-20240307",
            "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
        }
        actual_model = model_map.get(model, model)

        response = await self.client.messages.create(
            model=actual_model,
            max_tokens=max_tokens,
            system=system_content if system_content else None,
            messages=conversation_messages,
        )

        content = response.content[0].text if response.content else ""
        usage = {
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        }

        logger.info(f"Anthropic response: {len(content)} chars, usage={usage}")

        return LLMResponse(
            content=content,
            model=actual_model,
            usage=usage,
        )
