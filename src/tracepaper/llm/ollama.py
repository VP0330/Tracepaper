"""Ollama LLM client implementation."""

import json
from typing import Any

import requests

from .client import ChatResponse, ToolCall


class OllamaClient:
    """LLM client for Ollama using native /api/chat endpoint."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5:14b-instruct"):
        """
        Initialize Ollama client.

        Args:
            host: Ollama server URL.
            model: Model name to use.
        """
        self.host = host
        self.model = model
        self.chat_endpoint = f"{host}/api/chat"

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """
        Send a chat request to Ollama.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            tools: Optional list of tool definitions.
            json_schema: Optional JSON schema for structured output.

        Returns:
            ChatResponse with text, tool_calls, and usage.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        # Add format constraint if schema provided
        if json_schema:
            payload["format"] = json_schema

        # Note: Ollama native API has limited tool support compared to OpenAI.
        # For now, tools are included in the system message as context.
        if tools:
            # Prepend tool definitions to the messages
            tool_desc = self._format_tools(tools)
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += f"\n\n{tool_desc}"
            else:
                messages.insert(0, {"role": "system", "content": tool_desc})
            payload["messages"] = messages

        try:
            response = requests.post(self.chat_endpoint, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()

            # Extract response text
            text = data.get("message", {}).get("content", "")

            # Try to parse tool calls from response (model-dependent)
            tool_calls = self._parse_tool_calls(text)

            # Extract usage
            usage = {
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            }

            return ChatResponse(text=text, tool_calls=tool_calls, usage=usage)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API error: {e}") from e

    def _format_tools(self, tools: list[dict[str, Any]]) -> str:
        """Format tools for inclusion in system prompt."""
        if not tools:
            return ""

        tool_text = "Available tools:\n"
        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "")
            tool_text += f"- {name}: {description}\n"
        return tool_text

    def _parse_tool_calls(self, text: str) -> list[ToolCall] | None:
        """
        Attempt to parse tool calls from model response.

        For local models, tool calling is limited. This is a best-effort parser
        that looks for structured JSON in the response.
        """
        if not text:
            return None

        # Look for JSON-like tool call patterns
        # This is a simple heuristic; actual structured tool calling is limited in local models
        try:
            if "<tool_call>" in text or "tool_call" in text.lower():
                # Try to extract JSON
                import re

                json_match = re.search(r"\{.*\}", text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    data = json.loads(json_str)
                    if "name" in data and "arguments" in data:
                        return [ToolCall(name=data["name"], arguments=data["arguments"])]
        except Exception:
            pass

        return None
