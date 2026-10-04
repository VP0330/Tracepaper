"""Provider-agnostic Phase 4 agent loop."""

import json
from typing import Any

from tracepaper.llm.client import ChatResponse, LLMClient

from .enforcement import EnforcementPipeline, Finding
from .tools import EvidenceTools


TOOL_DEFINITIONS = [
    {"name": "search_evidence", "description": "Search indexed evidence.", "input_schema": {"type": "object"}},
    {"name": "fetch_page", "description": "Fetch chunks for a document page.", "input_schema": {"type": "object"}},
    {"name": "compare_dates", "description": "Compare ISO dates.", "input_schema": {"type": "object"}},
    {"name": "compare_amounts", "description": "Compare numeric amounts.", "input_schema": {"type": "object"}},
    {"name": "record_finding", "description": "Submit a citation-backed finding.", "input_schema": {"type": "object"}},
]


class AgentLoop:
    """Run bounded tool calls and enforce the final finding."""

    def __init__(self, client: LLMClient, tools: EvidenceTools, max_turns: int = 8):
        self.client = client
        self.tools = tools
        self.enforcement = EnforcementPipeline(tools)
        self.max_turns = max_turns

    def run(self, task: str) -> Finding:
        messages: list[dict[str, str]] = [{"role": "user", "content": task}]
        for _ in range(self.max_turns):
            response: ChatResponse = self.client.chat(messages, tools=TOOL_DEFINITIONS)
            if response.tool_calls:
                for call in response.tool_calls:
                    if call.name == "record_finding":
                        return self.enforcement.validate_finding(call.arguments)
                    result = self._dispatch(call.name, call.arguments)
                    messages.append({"role": "assistant", "content": json.dumps(call.arguments)})
                    messages.append({"role": "tool", "content": json.dumps(result)})
                continue
            if response.text:
                try:
                    return self.enforcement.validate_finding(json.loads(response.text))
                except (ValueError, json.JSONDecodeError):
                    messages.append({"role": "assistant", "content": response.text})
        raise RuntimeError("Agent did not produce a valid finding within max_turns")

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "search_evidence":
            return self.tools.search_evidence(**arguments)
        if name == "fetch_page":
            return self.tools.fetch_page(**arguments)
        if name == "compare_dates":
            return self.tools.compare_dates(**arguments)
        if name == "compare_amounts":
            return self.tools.compare_amounts(**arguments)
        raise ValueError(f"Unknown tool: {name}")
