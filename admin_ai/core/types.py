"""Neutral data types shared by Agent Core, providers and adapters. Standard library only."""
from dataclasses import dataclass
from typing import Any, Tuple


class AgentError(Exception):
    """Base error carrying a machine-readable code (never raw provider/database text)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProviderError(AgentError):
    """The AI provider failed or returned something unusable."""


class ToolError(AgentError):
    """A tool call was rejected or failed."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller on whose behalf the agent runs. Established by the host application only."""
    id: str
    role: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Any          # provider-parsed JSON; NOT trusted, validated by the registry


@dataclass(frozen=True)
class Message:
    role: str               # system | user | assistant | tool
    content: str = ""
    tool_calls: Tuple[ToolCall, ...] = ()
    tool_call_id: str = ""


@dataclass(frozen=True)
class ToolDefinition:
    """What a provider is told about a tool."""
    name: str
    description: str
    parameters: dict        # JSON Schema object


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    tool_calls: Tuple[ToolCall, ...] = ()
