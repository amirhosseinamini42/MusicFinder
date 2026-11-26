"""Allowlisted, permission-controlled tool registry. Standard library only.

Validation is injected by the adapter (`validate`), so the core needs no schema library.
Only read-only tools can be registered in this phase.
"""
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Tuple

from admin_ai.core.types import Principal, ToolDefinition, ToolError

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict                         # JSON Schema shown to the model
    validate: Callable[[dict], dict]         # raises on invalid input; returns clean keyword arguments
    handler: Callable[..., dict]
    allowed_roles: FrozenSet[str]
    read_only: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.read_only:
            raise ValueError("mutating tools are not supported in this phase")
        if not _NAME.match(spec.name):
            raise ValueError("invalid tool name")
        if spec.name in self._tools:
            raise ValueError("duplicate tool name")
        if not spec.allowed_roles:
            raise ValueError("a tool must declare at least one allowed role")
        self._tools[spec.name] = spec

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._tools))

    def definitions_for(self, principal: Principal) -> Tuple[ToolDefinition, ...]:
        """Only tools this principal may call are ever shown to the model."""
        return tuple(
            ToolDefinition(s.name, s.description, s.parameters)
            for s in self._tools.values() if principal.role in s.allowed_roles
        )

    def execute(self, principal: Principal, name: Any, arguments: Any) -> dict:
        spec = self._tools.get(name) if isinstance(name, str) else None
        if spec is None:
            raise ToolError("tool_not_allowed")
        if principal.role not in spec.allowed_roles:
            raise ToolError("tool_forbidden")
        if not isinstance(arguments, dict):
            raise ToolError("invalid_tool_arguments")
        try:
            clean = spec.validate(arguments)
        except Exception:                    # any validator failure means the arguments are rejected
            raise ToolError("invalid_tool_arguments") from None
        if not isinstance(clean, dict):
            raise ToolError("invalid_tool_arguments")
        try:
            result = spec.handler(**clean)
        except ToolError:
            raise
        except Exception:                    # execution boundary: never leak internals to the model
            raise ToolError("tool_failed") from None
        if not isinstance(result, dict):
            raise ToolError("tool_failed")
        return result
