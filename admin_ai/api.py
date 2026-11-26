"""HTTP surface for the admin AI agent. Mounted by main.py. Disabled unless ADMIN_AI_ENABLED=true.

Order of checks for every request: Google identity -> role looked up in mf_admins (existing
`current_admin`, no caching) -> feature flag -> per-admin rate limit -> input validation inside the agent.
Authentication therefore always precedes the feature-flag answer.
"""
import os
from typing import List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from admin import current_admin
from library import err
from admin_ai.adapters.musicfinder import SYSTEM_PROMPT, build_registry
from admin_ai.core.agent import Agent, MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES, MAX_USER_CHARS
from admin_ai.core.audit import LoggingAuditSink
from admin_ai.core.ratelimit import SlidingWindowLimiter
from admin_ai.core.types import AgentError, Message, Principal, ProviderError

agent_router = APIRouter(prefix="/admin/agent", tags=["admin-agent"])

_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)
_audit = LoggingAuditSink()
_registry = None


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: StrictStr = Field(max_length=MAX_HISTORY_CHARS)


class AgentChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: StrictStr = Field(min_length=1, max_length=MAX_USER_CHARS)
    history: List[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("blank message")
        return v


def _get_registry():
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


def _build_provider():
    """Provider selection lives here so the core never imports a vendor. Add new providers to this switch."""
    name = os.getenv("ADMIN_AI_PROVIDER", "avalai").strip().lower()
    if name != "avalai":
        raise err(503, "agent_not_configured")
    from admin_ai.providers.avalai import AvalAIProvider
    try:
        return AvalAIProvider()
    except ValueError:
        raise err(503, "agent_not_configured") from None


def agent_enabled(admin: dict = Depends(current_admin)) -> dict:
    if os.getenv("ADMIN_AI_ENABLED", "").strip().lower() != "true":
        raise err(503, "agent_disabled")
    return admin


@agent_router.post("/chat")
def chat(body: AgentChatIn, admin: dict = Depends(agent_enabled)):
    if not _limiter.allow(admin["email"]):
        raise err(429, "rate_limited")
    agent = Agent(provider=_build_provider(), registry=_get_registry(), audit=_audit, system_prompt=SYSTEM_PROMPT)
    history = [Message(t.role, t.content) for t in body.history]
    try:
        result = agent.run(Principal(admin["email"], admin["role"]), body.message, history)
    except ProviderError as e:
        raise err(502, e.code) from None
    except AgentError as e:
        raise err(422, e.code) from None
    return {
        "reply": result.reply, "status": result.status, "steps": result.steps, "run_id": result.run_id,
        "tool_calls": [{"name": t.name, "ok": t.ok, "error": t.error} for t in result.tool_calls],
    }
