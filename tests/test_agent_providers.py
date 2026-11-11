import json
import os
import unittest
from unittest import mock

import requests

from admin_ai.core.provider import AIProvider
from admin_ai.core.types import Message, ProviderError, ToolCall, ToolDefinition
from admin_ai.providers import avalai
from admin_ai.providers.avalai import AvalAIProvider, parse_chat_completion
from admin_ai.providers.base import AIProvider as BaseAIProvider

ENV = {"ADMIN_AI_API_KEY": "sk-test-SECRET", "ADMIN_AI_MODEL": "m", "ADMIN_AI_BASE_URL": "https://api.avalai.ir/v1"}


class FakeResp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._body


def completion(content="hi", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg}]}


def tc(id="c1", name="search_tracks", args='{"query":"a"}'):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": args}}


class ParseTests(unittest.TestCase):
    def test_text(self):
        r = parse_chat_completion(completion("hello"))
        self.assertEqual((r.content, r.tool_calls), ("hello", ()))

    def test_tool_calls_parsed(self):
        r = parse_chat_completion(completion(None, [tc()]))
        self.assertEqual(r.tool_calls, (ToolCall("c1", "search_tracks", {"query": "a"}),))

    def test_invalid_argument_json_becomes_none_not_provider_error(self):
        r = parse_chat_completion(completion(None, [tc(args="{not json")]))
        self.assertIsNone(r.tool_calls[0].arguments)

    def test_empty_arguments_string_is_empty_object(self):
        self.assertEqual(parse_chat_completion(completion(None, [tc(args="")])).tool_calls[0].arguments, {})

    def test_malformed_responses_rejected(self):
        bad = [None, [], "x", {}, {"choices": []}, {"choices": [None]}, {"choices": [{}]}, {"choices": [{"message": "x"}]},
               completion(5), completion(""), completion(None), completion("x" * 20001),
               completion("hi", "notalist"), completion(None, [None]), completion(None, [{"id": "", "function": {}}]),
               completion(None, [{"id": "1", "function": {"name": 5, "arguments": "{}"}}]),
               completion(None, [{"id": "1", "function": {"name": "a", "arguments": {}}}]),
               completion(None, [tc(id=str(i)) for i in range(9)])]
        for b in bad:
            with self.assertRaises(ProviderError, msg=repr(b)[:60]) as cm:
                parse_chat_completion(b)
            self.assertEqual(cm.exception.code, "provider_invalid_response")


class ProviderTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)

    def gen(self, resp=None, exc=None, messages=None, tools=()):
        with mock.patch.object(avalai.requests, "post", side_effect=exc, return_value=resp) as post:
            out = AvalAIProvider().generate(messages or [Message("user", "hi")], tools)
        return out, post

    def test_interface_and_compat_import(self):
        self.assertTrue(issubclass(AvalAIProvider, AIProvider))
        self.assertIs(BaseAIProvider, AIProvider)

    def test_success_and_request_shape(self):
        tools = [ToolDefinition("search_tracks", "d", {"type": "object"})]
        msgs = [Message("system", "s"), Message("user", "u"),
                Message("assistant", "", (ToolCall("c1", "search_tracks", {"query": "a"}),)),
                Message("tool", '{"ok":true}', tool_call_id="c1")]
        out, post = self.gen(FakeResp(body=completion("answer")), messages=msgs, tools=tools)
        self.assertEqual(out.content, "answer")
        kw = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], "https://api.avalai.ir/v1/chat/completions")
        self.assertFalse(kw["allow_redirects"])
        self.assertEqual(kw["headers"]["Authorization"], "Bearer sk-test-SECRET")
        wire = kw["json"]
        self.assertEqual(wire["tool_choice"], "auto")
        self.assertEqual(wire["tools"][0]["function"]["name"], "search_tracks")
        self.assertEqual(wire["messages"][2]["tool_calls"][0]["function"]["arguments"], '{"query":"a"}')
        self.assertEqual(wire["messages"][3], {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'})
        self.assertIsNone(wire["messages"][2]["content"])

    def test_no_tools_key_when_no_tools_offered(self):
        _, post = self.gen(FakeResp(body=completion("x")))
        self.assertNotIn("tools", post.call_args.kwargs["json"])
        self.assertNotIn("tool_choice", post.call_args.kwargs["json"])

    def test_failures_map_to_codes_without_leaking_key(self):
        cases = [
            (dict(exc=requests.Timeout("sk-test-SECRET")), "provider_timeout"),
            (dict(exc=requests.ConnectionError("sk-test-SECRET")), "provider_request_failed"),
            (dict(resp=FakeResp(status=500, body={})), "provider_request_failed"),
            (dict(resp=FakeResp(status=401, body={})), "provider_request_failed"),
            (dict(resp=FakeResp(status=302, body={})), "provider_request_failed"),
            (dict(resp=FakeResp(bad_json=True)), "provider_invalid_response"),
            (dict(resp=FakeResp(body=["x"])), "provider_invalid_response"),
            (dict(resp=FakeResp(body={"choices": []})), "provider_invalid_response"),
        ]
        for kwargs, code in cases:
            with self.assertRaises(ProviderError) as cm:
                self.gen(**kwargs)
            self.assertEqual(cm.exception.code, code)
            self.assertNotIn("SECRET", str(cm.exception))

    def test_configuration_checks(self):
        for patch in ({"ADMIN_AI_BASE_URL": "https://evil.example/v1"}, {"ADMIN_AI_API_KEY": ""}, {"ADMIN_AI_MODEL": ""}):
            with mock.patch.dict(os.environ, patch):
                with self.assertRaises(ValueError):
                    AvalAIProvider()


if __name__ == "__main__":
    unittest.main()
