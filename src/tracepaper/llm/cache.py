"""Database-backed cache for LLM responses."""

import hashlib
import json
from typing import Any

from sqlalchemy import select

from tracepaper.storage.db import get_engine, get_session_factory, init_db
from tracepaper.storage.models import LLMCacheRecord

from .client import ChatResponse, LLMClient, ToolCall


class DatabaseCachedLLMClient:
    """Cache model responses in the configured application database."""

    def __init__(self, client: LLMClient, database_url: str):
        self.client = client
        self.model = getattr(client, "model", client.__class__.__name__)
        self.engine = get_engine(database_url)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)

    def _key(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None,
             schema: dict[str, Any] | None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "schema": schema,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def chat(self, messages, tools=None, json_schema=None) -> ChatResponse:
        cache_key = self._key(messages, tools, json_schema)
        with self.session_factory() as session:
            cached = session.get(LLMCacheRecord, cache_key)
            if cached is not None:
                body = cached.response_body
                calls = [ToolCall(name=call["name"], arguments=call["arguments"])
                         for call in body.get("tool_calls", [])]
                return ChatResponse(text=body.get("text"), tool_calls=calls or None, usage=body.get("usage"))

        response = self.client.chat(messages, tools, json_schema)
        body = {
            "text": response.text,
            "tool_calls": [{"name": call.name, "arguments": call.arguments} for call in (response.tool_calls or [])],
            "usage": response.usage,
        }
        with self.session_factory() as session:
            session.merge(LLMCacheRecord(cache_key=cache_key, response_body=body))
            session.commit()
        return response