"""Anthropic LLM client implementation."""

from typing import Any

import anthropic

from .client import ChatResponse, ToolCall


class AnthropicClient:
    """LLM client for Anthropic Claude models."""

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var).
            model: Model name to use.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """
        Send a chat request to Anthropic API.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            tools: Optional list of tool definitions (Anthropic tool_use format).
            json_schema: Optional JSON schema (converted to Anthropic format if needed).

        Returns:
            ChatResponse with text, tool_calls, and usage.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
        }

        # Add tools if provided
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)

            # Extract text content
            text = ""
            tool_calls = []

            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text
                elif hasattr(block, "type") and block.type == "tool_use":
                    tool_calls.append(ToolCall(name=block.name, arguments=block.input))

            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            return ChatResponse(
                text=text if text else None,
                tool_calls=tool_calls if tool_calls else None,
                usage=usage,
            )
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e
