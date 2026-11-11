"""Agent orchestration loop. Standard library only; no knowledge of any application or AI vendor.

Flow per run: audit start -> [provider call -> (tool calls: authorize, validate, execute, audit)]* -> reply.
Bounded by max_steps, max tool calls per step and a wall-clock budget. On the last step the model is
called WITHOUT tools so it must answer from what it has gathered. Planning is prompt-guided (see the
adapter's system prompt); there is no separate planner component.
"""
import json
import time
import uuid
from dataclasses import dataclass
from typing import Callable, List, Sequence, Tuple

from admin_ai.core.audit import AuditEvent, AuditSink, args_digest
from admin_ai.core.provider import AIProvider
from admin_ai.core.registry import ToolRegistry
from admin_ai.core.types import AgentError, Message, Principal, ProviderError, ToolCall, ToolError

MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 4000
MAX_USER_CHARS = 2000
MAX_TOOL_RESULT_CHARS = 60000


@dataclass(frozen=True)
class ToolTrace:
    name: str
    ok: bool
    error: str = ""


@dataclass(frozen=True)
class AgentResult:
    reply: str
    status: str                      # completed | step_limit | time_limit
    steps: int
    tool_calls: Tuple[ToolTrace, ...]
    run_id: str


class Agent:
    def __init__(self, provider: AIProvider, registry: ToolRegistry, audit: AuditSink, system_prompt: str,
                 max_steps: int = 4, max_tool_calls_per_step: int = 4, deadline_seconds: float = 45.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if max_steps < 1 or max_tool_calls_per_step < 1:
            raise ValueError("limits must be >= 1")
        self.provider, self.registry, self.audit = provider, registry, audit
        self.system_prompt, self.max_steps = system_prompt, max_steps
        self.max_tool_calls_per_step, self.deadline_seconds, self._clock = max_tool_calls_per_step, deadline_seconds, clock

    # ---- helpers ----
    def _emit(self, run_id: str, principal: Principal, event: str, **data) -> None:
        self.audit.record(AuditEvent(run_id, event, principal.id, principal.role, data))

    @staticmethod
    def _check_history(history: Sequence[Message]) -> List[Message]:
        """Client-supplied history is untrusted: only plain user/assistant text, bounded in size."""
        if len(history) > MAX_HISTORY_MESSAGES:
            raise AgentError("invalid_history")
        out = []
        for m in history:
            if (not isinstance(m, Message) or m.role not in ("user", "assistant") or m.tool_calls
                    or m.tool_call_id or not isinstance(m.content, str) or len(m.content) > MAX_HISTORY_CHARS):
                raise AgentError("invalid_history")
            out.append(Message(m.role, m.content))
        return out

    def _run_tool(self, run_id: str, principal: Principal, call: ToolCall) -> Tuple[Message, ToolTrace]:
        name = call.name if isinstance(call.name, str) else ""
        try:
            result = self.registry.execute(principal, call.name, call.arguments)
            content = json.dumps({"ok": True, "data": result}, default=str, ensure_ascii=False)
            if len(content) > MAX_TOOL_RESULT_CHARS:
                raise ToolError("tool_result_too_large")
            trace = ToolTrace(name, True)
        except ToolError as e:
            content = json.dumps({"ok": False, "error": e.code})
            trace = ToolTrace(name, False, e.code)
        self._emit(run_id, principal, "tool_call", tool=name[:64], args_sha256=args_digest(call.arguments),
                   ok=trace.ok, error=trace.error)
        return Message("tool", content, tool_call_id=call.id), trace

    # ---- main entry ----
    def run(self, principal: Principal, user_message: str, history: Sequence[Message] = ()) -> AgentResult:
        run_id = uuid.uuid4().hex
        if not isinstance(user_message, str) or not user_message.strip() or len(user_message) > MAX_USER_CHARS:
            raise AgentError("invalid_message")
        messages: List[Message] = [Message("system", self.system_prompt), *self._check_history(history),
                                   Message("user", user_message)]
        tools = self.registry.definitions_for(principal)
        traces: List[ToolTrace] = []
        started = self._clock()
        self._emit(run_id, principal, "run_started", message_chars=len(user_message), history=len(history),
                   tools=[t.name for t in tools])

        for step in range(1, self.max_steps + 1):
            if self._clock() - started > self.deadline_seconds:
                self._emit(run_id, principal, "run_finished", status="time_limit", steps=step - 1)
                return AgentResult("", "time_limit", step - 1, tuple(traces), run_id)
            offered = tools if step < self.max_steps else ()
            try:
                response = self.provider.generate(messages, offered)
            except ProviderError as e:
                self._emit(run_id, principal, "provider_error", code=e.code, step=step)
                raise
            except Exception:                                # a buggy provider must not leak internals
                self._emit(run_id, principal, "provider_error", code="provider_failed", step=step)
                raise ProviderError("provider_failed") from None

            if not response.tool_calls:
                self._emit(run_id, principal, "run_finished", status="completed", steps=step)
                return AgentResult(response.content, "completed", step, tuple(traces), run_id)
            if not offered:                                  # tools were not offered but requested anyway
                break
            if len(response.tool_calls) > self.max_tool_calls_per_step:
                self._emit(run_id, principal, "run_finished", status="too_many_tool_calls", steps=step)
                raise AgentError("too_many_tool_calls")

            messages.append(Message("assistant", response.content, tuple(response.tool_calls)))
            for call in response.tool_calls:
                tool_msg, trace = self._run_tool(run_id, principal, call)
                messages.append(tool_msg)
                traces.append(trace)

        self._emit(run_id, principal, "run_finished", status="step_limit", steps=self.max_steps)
        return AgentResult("", "step_limit", self.max_steps, tuple(traces), run_id)
