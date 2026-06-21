from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agent_server import AGENTS, call_gemini, decrypt_api_key


def _encrypt_api_key(plain_text: str, secret: str) -> str:
    import base64
    import hashlib
    import hmac

    salt = b"0123456789abcdef"
    nonce = b"abcdef0123456789"
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 200000, dklen=32)
    ciphertext = bytes(
        byte ^ key[index % len(key)] ^ nonce[index % len(nonce)]
        for index, byte in enumerate(plain_text.encode("utf-8"))
    )
    signature = hmac.new(key, salt + nonce + ciphertext, hashlib.sha256).digest()
    payload = salt + nonce + ciphertext + signature
    return base64.urlsafe_b64encode(payload).decode("utf-8")


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class AgentServerProviderTests(unittest.TestCase):
    def test_decrypt_api_key_success(self):
        encrypted = _encrypt_api_key("demo-key", "secret-123")
        self.assertEqual("demo-key", decrypt_api_key(encrypted, "secret-123"))

    def test_decrypt_api_key_rejects_invalid_payload(self):
        with self.assertRaisesRegex(ValueError, "invalid"):
            decrypt_api_key("bm90LWEtdmFsaWQtdG9rZW4=", "secret-123")

    def test_call_gemini_requires_api_key(self):
        any_agent = next(iter(AGENTS.values()))
        with patch("agent_server.GEMINI_API_KEY", ""):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                call_gemini(any_agent, "hello", "gemini-1.5-flash")

    @patch("agent_server.urllib.request.urlopen")
    def test_call_gemini_returns_text_response(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))
        mocked_urlopen.return_value = _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Line 1"},
                                {"text": "Line 2"},
                            ]
                        }
                    }
                ]
            }
        )
        with patch("agent_server.GEMINI_API_KEY", "demo-key"):
            result = call_gemini(any_agent, "hello", "gemini-1.5-flash")
        self.assertEqual("Line 1\nLine 2", result)


if __name__ == "__main__":
    unittest.main()
