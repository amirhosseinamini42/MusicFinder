from admin_ai.core.provider import AIProvider
from admin_ai.core.registry import ToolRegistry, ToolSpec
from admin_ai.core.types import ProviderResponse, ToolCall


class ScriptedProvider(AIProvider):
    """Returns scripted responses in order; raises scripted exceptions. Records every call."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def generate(self, messages, tools):
        self.calls.append((list(messages), tuple(tools)))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def text(s):
    return ProviderResponse(content=s)


def call(name, args, cid="c1"):
    return ToolCall(cid, name, args)


def tool_response(*calls):
    return ProviderResponse(content="", tool_calls=tuple(calls))


def _validate_echo(args):
    if set(args) != {"text"} or not isinstance(args["text"], str):
        raise ValueError("bad")
    return {"text": args["text"]}


def make_registry(calls_log=None):
    log = calls_log if calls_log is not None else []
    reg = ToolRegistry()

    def echo(text):
        log.append(("echo", text))
        return {"echo": text}

    def boom():
        raise RuntimeError("secret-db-password")

    def big():
        return {"blob": "x" * 70000}

    reg.register(ToolSpec("echo", "Echo", {"type": "object"}, _validate_echo, echo, frozenset({"admin", "owner"})))
    reg.register(ToolSpec("boom", "Boom", {"type": "object"}, lambda a: {}, boom, frozenset({"admin", "owner"})))
    reg.register(ToolSpec("big", "Big", {"type": "object"}, lambda a: {}, big, frozenset({"admin", "owner"})))
    reg.register(ToolSpec("owner_only", "Owner", {"type": "object"}, lambda a: {}, lambda: {"ok": 1}, frozenset({"owner"})))
    return reg
