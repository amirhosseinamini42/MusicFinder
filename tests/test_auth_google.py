import os
import time
import unittest
from unittest import mock

import requests
from fastapi import HTTPException

import auth_google

CID = "client-123.apps.googleusercontent.com"


class Resp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._b, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("x")
        return self._b


def info(**over):
    base = {"aud": CID, "iss": "https://accounts.google.com", "exp": str(int(time.time()) + 3600), "sub": "123",
            "email": "Admin@Example.com", "email_verified": "true", "name": "Admin"}
    base.update(over)
    return base


class AuthGoogleTests(unittest.TestCase):
    def setUp(self):
        auth_google._cache.clear()
        p = mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": CID})
        p.start()
        self.addCleanup(p.stop)

    def verify(self, resp=None, exc=None, token="tok"):
        with mock.patch.object(auth_google.requests, "get", side_effect=exc, return_value=resp) as g:
            return auth_google.verify_google(token), g

    def code(self, **kw):
        with self.assertRaises(HTTPException) as cm:
            self.verify(**kw)
        return cm.exception.status_code, cm.exception.detail["code"]

    def test_valid_token_normalizes_email(self):
        ident, g = self.verify(Resp(body=info()))
        self.assertEqual(ident, {"sub": "123", "email": "admin@example.com", "name": "Admin"})
        self.assertFalse(g.call_args.kwargs["allow_redirects"])

    def test_rejections(self):
        cases = [
            (Resp(status=400, body={}), (401, "session_expired")),
            (Resp(body=info(aud="other")), (401, "session_expired")),
            (Resp(body=info(iss="https://evil.example")), (401, "session_expired")),
            (Resp(body=info(exp=str(int(time.time()) - 5))), (401, "session_expired")),
            (Resp(body=info(exp="abc")), (401, "session_expired")),
            (Resp(body=info(sub="")), (401, "session_expired")),
            (Resp(body=info(email="")), (401, "session_expired")),
            (Resp(body=info(email_verified="false")), (401, "email_not_verified")),
            (Resp(body=info(email_verified=None)), (401, "email_not_verified")),
            (Resp(body=["x"]), (401, "session_expired")),
            (Resp(bad_json=True), (502, "auth_unavailable")),
        ]
        for resp, expected in cases:
            auth_google._cache.clear()
            self.assertEqual(self.code(resp=resp), expected)
        self.assertEqual(self.code(exc=requests.ConnectionError("x")), (502, "auth_unavailable"))

    def test_missing_client_id(self):
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": ""}):
            self.assertEqual(self.code(resp=Resp(body=info())), (503, "cloud_not_configured"))

    def test_identity_cached_but_failures_are_not(self):
        _, g = self.verify(Resp(body=info()))
        with mock.patch.object(auth_google.requests, "get") as g2:
            auth_google.verify_google("tok")
            g2.assert_not_called()
        self.assertEqual(self.code(resp=Resp(status=400, body={}), token="other"), (401, "session_expired"))

    def test_bearer_parsing(self):
        self.assertEqual(auth_google.bearer_token("Bearer abc"), "abc")
        self.assertEqual(auth_google.bearer_token("bearer  abc "), "abc")
        for bad in (None, "", "Basic abc", "Bearer", "Bearer   "):
            with self.assertRaises(HTTPException) as cm:
                auth_google.bearer_token(bad)
            self.assertEqual(cm.exception.detail["code"], "auth_required")
        with self.assertRaises(HTTPException):
            auth_google.bearer_token("Bearer " + "a" * 5000)


if __name__ == "__main__":
    unittest.main()
