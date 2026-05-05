import os
from typing import List
import logging
from openai import AsyncOpenAI

from ..base import LLMService, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

# Models that use the new responses.create API
NEW_API_MODELS = {"gpt-4.1", "gpt-5", "gpt-5.2", "gpt-5-nano", "gpt-5-mini"}

# Models that support reasoning (GPT-5 family)
REASONING_MODELS = {"gpt-5", "gpt-5.2", "gpt-5-nano", "gpt-5-mini"}


class OpenAIService(LLMService):
    """OpenAI LLM service implementation."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set - OpenAI calls will fail")
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def generate(
        self,
        messages: List[LLMMessage],
        model: str = "gpt-4.1",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response using OpenAI API."""
        if not self.client:
            logger.error("OpenAI client not initialized - missing API key")
            return LLMResponse(
                content="[Error: OpenAI API key not configured]",
                model=model,
            )

        logger.info(f"OpenAI generate: model={model}, messages={len(messages)}")

        # Use new responses.create API for new models
        if model in NEW_API_MODELS:
            return await self._generate_new_api(messages, model, temperature, max_tokens)
        else:
            # Fallback to legacy chat.completions API for older models
            return await self._generate_legacy_api(messages, model, temperature, max_tokens)

    async def _generate_new_api(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate using the new responses.create API (GPT-4.1, GPT-5 family)."""

        # Convert messages to input format
        input_messages = []
        for msg in messages:
            if msg.role == "system":
                input_messages.append({
                    "role": "system",
                    "content": msg.content
                })
            elif msg.role == "user":
                input_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == "assistant":
                input_messages.append({
                    "role": "assistant",
                    "content": msg.content
                })

        # Build request parameters based on model type
        if model in REASONING_MODELS:
            # GPT-5 family: uses verbosity and reasoning effort
            response = await self.client.responses.create(
                model=model,
                input=input_messages,
                text={
                    "format": {
                        "type": "text"
                    },
                    "verbosity": "low"
                },
                reasoning={
                    # OpenAI deprecated 'none' for gpt-5; supported values are
                    # 'minimal' / 'low' / 'medium' / 'high'. Use 'minimal' for
                    # cheapest+fastest path (matches the previous 'none' intent).
                    "effort": "minimal"
                },
                # HIDDEN: web search tool
                # tools=[{"type": "web_search"}],
                store=True,
                # include=[
                #     "reasoning.encrypted_content",
                #     "web_search_call.action.sources"
                # ]
            )
        else:
            # GPT-4.1: uses temperature and max_output_tokens
            response = await self.client.responses.create(
                model=model,
                input=input_messages,
                text={
                    "format": {
                        "type": "text"
                    }
                },
                reasoning={},
                # HIDDEN: web search tool
                # tools=[{"type": "web_search"}],
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=1,
                store=True,
                # include=["web_search_call.action.sources"]
            )

        # Extract content from response
        content = self._extract_response_content(response)

        # Extract usage if available
        usage = {}
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "input_tokens": getattr(response.usage, 'input_tokens', 0),
                "output_tokens": getattr(response.usage, 'output_tokens', 0),
                "total_tokens": getattr(response.usage, 'total_tokens', 0),
            }

        logger.info(f"OpenAI response (new API): {len(content)} chars, usage={usage}")

        from ...humaneval.cost_tracker import record_usage
        record_usage(usage)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
        )

    async def _generate_legacy_api(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate using the legacy chat.completions API (gpt-4o, etc.)."""

        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        response = await self.client.chat.completions.create(
            model=model,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        logger.info(f"OpenAI response (legacy API): {len(content)} chars, usage={usage}")

        from ...humaneval.cost_tracker import record_usage
        record_usage(usage)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
        )

    def _extract_response_content(self, response) -> str:
        """Extract text content from the new API response format."""
        # The new API response structure may vary
        # Try different ways to extract the content

        # Check for output_text attribute
        if hasattr(response, 'output_text') and response.output_text:
            return response.output_text

        # Check for output list with text items
        if hasattr(response, 'output') and response.output:
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message':
                    if hasattr(item, 'content') and item.content:
                        for content_item in item.content:
                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                if hasattr(content_item, 'text'):
                                    return content_item.text
                            elif hasattr(content_item, 'text'):
                                return content_item.text

        # Check for text attribute directly
        if hasattr(response, 'text') and response.text:
            return response.text

        # Check for content attribute
        if hasattr(response, 'content') and response.content:
            return response.content

        # Fallback: try to convert response to string
        logger.warning(f"Could not extract content from response, using str(): {type(response)}")
        return str(response)
