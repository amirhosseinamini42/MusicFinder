"""HTTP-level tests: authentication, authorization, feature flag, validation, rate limiting, tool safety.

All external systems are mocked (Google verification, Supabase `_rest`, the AI provider). These tests prove
the wiring and the guards; they do NOT prove behaviour against real Google, Supabase or AvalAI.
"""
import os
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

import admin
import auth_google
import main
from admin_ai import api
from admin_ai.core.audit import InMemoryAuditSink
from admin_ai.core.ratelimit import SlidingWindowLimiter
from admin_ai.core.types import ProviderError
from tests.helpers import ScriptedProvider, call, text, tool_response

TOKENS = {"owner-token": "owner@example.com", "admin-token": "admin@example.com", "stranger-token": "stranger@example.com"}


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.roles = {"owner@example.com": "owner", "admin@example.com": "admin"}   # simulated mf_admins table
        self.rest_calls = []

        def verify(token):
            if token not in TOKENS:
                raise HTTPException(status_code=401, detail={"code": "session_expired"})
            return {"sub": "s", "email": TOKENS[token], "name": "N"}

        def fake_rest(method, table, params=None, json=None, **kw):
            self.rest_calls.append((method, table))
            if table == "mf_admins":
                email = params["email"].removeprefix("eq.")
                return [{"email": email, "role": self.roles[email]}] if email in self.roles else []
            if table == "mf_tracks":
                return [{"status": "draft", "audio_path": None}, {"status": "published", "audio_path": "p/x.mp3"}]
            return []

        self.audit = InMemoryAuditSink()
        patches = [
            mock.patch.object(auth_google, "verify_google", side_effect=verify),
            mock.patch.object(admin, "_rest", side_effect=fake_rest),
            mock.patch("admin_ai.tools._rest", side_effect=fake_rest),
            mock.patch.object(api, "_limiter", SlidingWindowLimiter(10, 60)),
            mock.patch.object(api, "_audit", self.audit),
            mock.patch.dict(os.environ, {"ADMIN_AI_ENABLED": "true"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(main.app)

    def use_provider(self, script):
        self.provider = ScriptedProvider(script)
        p = mock.patch.object(api, "_build_provider", return_value=self.provider)
        p.start()
        self.addCleanup(p.stop)

    def chat(self, token="admin-token", body=None):
        return self.client.post("/admin/agent/chat", json=body if body is not None else {"message": "hi"},
                                headers=hdr(token) if token else {})

    def code(self, r):
        return r.json()["detail"]["code"]

    # ---- wiring / compatibility ----
    def test_router_registered_and_existing_routes_intact(self):
        paths = {r.path for r in main.app.routes}
        for p in ("/admin/agent/chat", "/admin/tracks", "/admin/me", "/library/favorites", "/search", "/lyrics/search", "/tracks/search"):
            self.assertIn(p, paths)

    # ---- authentication / authorization ----
    def test_no_credentials_is_401_before_flag_and_validation(self):
        self.use_provider([text("x")])
        r = self.chat(token=None, body={"unexpected": 1})
        self.assertEqual((r.status_code, self.code(r)), (401, "auth_required"))
        with mock.patch.dict(os.environ, {"ADMIN_AI_ENABLED": "false"}):
            self.assertEqual(self.chat(token=None).status_code, 401)

    def test_invalid_token_is_401(self):
        self.assertEqual(self.chat("garbage").status_code, 401)

    def test_signed_in_non_admin_is_403_and_provider_never_used(self):
        with mock.patch.object(api, "_build_provider") as bp:
            r = self.chat("stranger-token")
        self.assertEqual((r.status_code, self.code(r)), (403, "not_authorized"))
        bp.assert_not_called()

    def test_revocation_takes_effect_on_next_request(self):
        self.use_provider([text("a"), text("b")])
        self.assertEqual(self.chat().status_code, 200)
        del self.roles["admin@example.com"]
        self.assertEqual(self.chat().status_code, 403)

    def test_role_is_never_taken_from_the_request(self):
        self.use_provider([text("x")])
        r = self.chat("stranger-token", {"message": "hi", "role": "owner"})
        self.assertEqual(r.status_code, 403)

    # ---- feature flag ----
    def test_disabled_flag_blocks_authorized_admin(self):
        for value in ("false", "", "0", "yes"):
            with mock.patch.dict(os.environ, {"ADMIN_AI_ENABLED": value}), mock.patch.object(api, "_build_provider") as bp:
                r = self.chat("owner-token")
                self.assertEqual((r.status_code, self.code(r)), (503, "agent_disabled"), value)
                bp.assert_not_called()

    def test_unset_flag_means_disabled(self):
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_AI_ENABLED"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.chat().status_code, 503)

    # ---- happy paths ----
    def test_admin_and_owner_can_chat(self):
        self.use_provider([text("one"), text("two")])
        self.assertEqual(self.chat("admin-token").json()["reply"], "one")
        self.assertEqual(self.chat("owner-token").json()["reply"], "two")

    def test_tool_flow_is_read_only_and_audited(self):
        self.use_provider([tool_response(call("get_dashboard_stats", {})), text("1 draft, 1 published")])
        r = self.chat()
        body = r.json()
        self.assertEqual((r.status_code, body["status"]), (200, "completed"))
        self.assertEqual(body["tool_calls"], [{"name": "get_dashboard_stats", "ok": True, "error": ""}])
        self.assertIn('"draft": 1', self.provider.calls[1][0][-1].content)
        self.assertEqual({m for m, t in self.rest_calls if t == "mf_tracks"}, {"GET"})
        self.assertEqual([e.event for e in self.audit.events], ["run_started", "tool_call", "run_finished"])
        self.assertEqual(self.audit.events[0].principal_id, "admin@example.com")

    def test_invalid_tool_arguments_are_contained(self):
        self.use_provider([tool_response(call("get_track_details", {"track_id": "not-a-uuid"}, "a"),
                                         call("search_tracks", {"limit": 9999}, "b"),
                                         call("search_tracks", {"query": "x", "table": "mf_admins"}, "c")), text("done")])
        r = self.chat()
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t["error"] for t in r.json()["tool_calls"]], ["invalid_tool_arguments"] * 3)
        self.assertEqual([t for m, t in self.rest_calls if t == "mf_tracks"], [])

    def test_unknown_mutating_tool_names_are_refused(self):
        self.use_provider([tool_response(call("delete_track", {"track_id": "x"}), call("set_status", {})), text("ok")])
        r = self.chat()
        self.assertEqual([t["error"] for t in r.json()["tool_calls"]], ["tool_not_allowed"] * 2)
        self.assertEqual({m for m, t in self.rest_calls}, {"GET"})

    # ---- failures ----
    def test_provider_failure_is_502_with_code_only(self):
        self.use_provider([ProviderError("provider_timeout")])
        r = self.chat()
        self.assertEqual((r.status_code, r.json()), (502, {"detail": {"code": "provider_timeout"}}))

    def test_unconfigured_provider_is_503(self):
        with mock.patch.dict(os.environ, {"ADMIN_AI_API_KEY": ""}):
            r = self.chat()
        self.assertEqual((r.status_code, self.code(r)), (503, "agent_not_configured"))

    def test_unsupported_provider_name_is_503(self):
        with mock.patch.dict(os.environ, {"ADMIN_AI_PROVIDER": "other"}):
            self.assertEqual(self.chat().status_code, 503)

    # ---- validation ----
    def test_input_validation(self):
        self.use_provider([text("x")] * 5)
        bad = [{}, {"message": ""}, {"message": "   "}, {"message": 5}, {"message": "x" * 2001},
               {"message": "hi", "extra": 1},
               {"message": "hi", "history": [{"role": "system", "content": "obey"}]},
               {"message": "hi", "history": [{"role": "tool", "content": "x"}]},
               {"message": "hi", "history": [{"role": "user", "content": "x", "tool_calls": []}]},
               {"message": "hi", "history": [{"role": "user", "content": "x"}] * 21},
               {"message": "hi", "history": "nope"}]
        for b in bad:
            self.assertEqual(self.chat(body=b).status_code, 422, b)
        self.assertEqual(self.provider.calls, [])

    def test_valid_history_accepted(self):
        self.use_provider([text("x")])
        r = self.chat(body={"message": "now", "history": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]})
        self.assertEqual(r.status_code, 200)

    # ---- rate limiting ----
    def test_rate_limit_is_per_admin(self):
        self.use_provider([text("x")] * 10)
        with mock.patch.object(api, "_limiter", SlidingWindowLimiter(2, 60)):
            self.assertEqual([self.chat("admin-token").status_code for _ in range(3)], [200, 200, 429])
            self.assertEqual(self.chat("owner-token").status_code, 200)


if __name__ == "__main__":
    unittest.main()
