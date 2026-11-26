import json
import os
from typing import Any, Sequence

import requests

from admin_ai.core.types import Message, ProviderResponse, ToolCall, ToolDefinition
from admin_ai.providers.base import AIProvider, ProviderError

MAX_TOOL_CALLS_ACCEPTED = 8
MAX_CONTENT_CHARS = 20000


def _to_wire_message(m: Message) -> dict:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    if m.role == "assistant" and m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": json.dumps(c.arguments, separators=(",", ":"))}}
                for c in m.tool_calls
            ],
        }
    return {"role": m.role, "content": m.content}


def _to_wire_tool(t: ToolDefinition) -> dict:
    return {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}


def parse_chat_completion(result: Any) -> ProviderResponse:
    """Strictly validate an OpenAI-compatible chat completion and convert it to the neutral response."""
    bad = ProviderError("provider_invalid_response")
    if not isinstance(result, dict):
        raise bad
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise bad
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise bad
    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str) or len(content) > MAX_CONTENT_CHARS:
        raise bad
    raw_calls = message.get("tool_calls")
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list) or len(raw_calls) > MAX_TOOL_CALLS_ACCEPTED:
        raise bad
    calls = []
    for rc in raw_calls:
        fn = rc.get("function") if isinstance(rc, dict) else None
        if (not isinstance(fn, dict) or not isinstance(rc.get("id"), str) or not rc["id"]
                or not isinstance(fn.get("name"), str) or not isinstance(fn.get("arguments"), str)):
            raise bad
        try:
            args = json.loads(fn["arguments"] or "{}")
        except ValueError:
            args = None                      # not an object -> the registry rejects it as invalid_tool_arguments
        calls.append(ToolCall(rc["id"], fn["name"], args))
    if not calls and not content.strip():
        raise bad
    return ProviderResponse(content=content, tool_calls=tuple(calls))


class AvalAIProvider(AIProvider):
    """OpenAI-compatible AvalAI provider."""

    def __init__(self):
        self.base_url = os.getenv(
            "ADMIN_AI_BASE_URL", "https://api.avalai.ir/v1"
        ).rstrip("/")
        self.api_key = os.getenv("ADMIN_AI_API_KEY", "").strip()
        self.model = os.getenv("ADMIN_AI_MODEL", "gpt-4.1-mini").strip()

        if self.base_url != "https://api.avalai.ir/v1":
            raise ValueError("Unsupported AvalAI base URL")

        if not self.api_key or not self.model:
            raise ValueError("AvalAI configuration is incomplete")

    def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> ProviderResponse:
        url = f"{self.base_url}/chat/completions"

        payload: dict = {
            "model": self.model,
            "messages": [_to_wire_message(m) for m in messages],
        }
        if tools:
            payload["tools"] = [_to_wire_tool(t) for t in tools]
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(10, 45),
                allow_redirects=False,       # never forward the API key to a redirect target
            )
            if response.status_code != 200:
                raise ProviderError("provider_request_failed")
            result = response.json()

        except ProviderError:
            raise
        except requests.Timeout:
            raise ProviderError("provider_timeout") from None
        except requests.RequestException:
            raise ProviderError("provider_request_failed") from None
        except ValueError:
            raise ProviderError("provider_invalid_response") from None

        return parse_chat_completion(result)
