from __future__ import annotations

import json
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import agent_server
from agent_server import AGENTS, call_gemini, call_grok, decrypt_api_key, get_cloud_model_options, resolve_cloud_model_credentials


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


class _FakeHttpError(urllib.error.HTTPError):
    def __init__(self, url: str, code: int, body: str = ""):
        super().__init__(url=url, code=code, msg="error", hdrs=None, fp=None)
        self._body = body.encode("utf-8")

    def read(self):
        return self._body


class AgentServerProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp_config = Path("_temp_cloud_providers_test.json")

    def tearDown(self):
        if self.temp_config.exists():
            self.temp_config.unlink()

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

    def test_call_grok_requires_api_key(self):
        any_agent = next(iter(AGENTS.values()))
        with self.assertRaisesRegex(ValueError, "API key"):
            call_grok(any_agent, "hello", "grok-2", api_key="")

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

    @patch("agent_server.urllib.request.urlopen")
    def test_call_gemini_retries_api_version_on_404_and_resolves_alias_model(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))

        def _urlopen_side_effect(request, timeout=0):
            if "/v1/models/" in request.full_url:
                raise _FakeHttpError(request.full_url, 404, '{"error":"not found"}')
            return _FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "ok"},
                                ]
                            }
                        }
                    ]
                }
            )

        mocked_urlopen.side_effect = _urlopen_side_effect
        with patch("agent_server.GEMINI_API_KEY", "demo-key"):
            result = call_gemini(any_agent, "hello", "gemini-1.5-flash")

        self.assertEqual("ok", result)
        called_urls = [args[0].full_url for args, _ in mocked_urlopen.call_args_list]
        self.assertTrue(any("/v1/models/gemini-2.5-flash-lite:generateContent" in url for url in called_urls))
        self.assertTrue(any("/v1beta/models/gemini-2.5-flash-lite:generateContent" in url for url in called_urls))

    @patch("agent_server.urllib.request.urlopen")
    def test_call_grok_uses_openai_compatible_chat_completions_endpoint(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))
        mocked_urlopen.return_value = _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "grok-output"
                        }
                    }
                ]
            }
        )

        result = call_grok(any_agent, "hello", "grok-2", api_key="demo-key")
        self.assertEqual("grok-output", result)

        request = mocked_urlopen.call_args[0][0]
        self.assertIn("/v1/chat/completions", request.full_url)
        self.assertEqual("Bearer demo-key", request.headers.get("Authorization"))

    @patch("agent_server.urllib.request.urlopen")
    def test_call_grok_retries_responses_endpoint_after_chat_400(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))

        def _urlopen_side_effect(request, timeout=0):
            if request.full_url.endswith("/v1/chat/completions"):
                raise _FakeHttpError(request.full_url, 400, '{"error":{"message":"bad chat payload"}}')
            return _FakeResponse({"output_text": "responses-output"})

        mocked_urlopen.side_effect = _urlopen_side_effect
        result = call_grok(any_agent, "hello", "grok-2", api_key="demo-key")
        self.assertEqual("responses-output", result)

        called_urls = [args[0].full_url for args, _ in mocked_urlopen.call_args_list]
        self.assertTrue(any(url.endswith("/v1/chat/completions") for url in called_urls))
        self.assertTrue(any(url.endswith("/v1/responses") for url in called_urls))

    @patch("agent_server.urllib.request.urlopen")
    def test_call_grok_surfaces_error_body_when_requests_fail(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))

        def _urlopen_side_effect(request, timeout=0):
            if request.full_url.endswith("/v1/chat/completions"):
                raise _FakeHttpError(request.full_url, 400, '{"error":{"message":"chat failed"}}')
            raise _FakeHttpError(request.full_url, 400, '{"error":{"message":"responses failed"}}')

        mocked_urlopen.side_effect = _urlopen_side_effect
        with self.assertRaisesRegex(ValueError, "responses failed"):
            call_grok(any_agent, "hello", "grok-2", api_key="demo-key")

    @patch("agent_server.urllib.request.urlopen")
    def test_call_groq_retries_non_openai_path_on_403_1010(self, mocked_urlopen):
        any_agent = next(iter(AGENTS.values()))

        def _urlopen_side_effect(request, timeout=0):
            if request.full_url == "https://api.groq.com/openai/v1/chat/completions":
                raise _FakeHttpError(request.full_url, 403, "error code: 1010")
            if request.full_url == "https://api.groq.com/v1/chat/completions":
                return _FakeResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "groq-fallback-ok",
                                }
                            }
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL: {request.full_url}")

        mocked_urlopen.side_effect = _urlopen_side_effect

        with patch("agent_server.GROQ_API_BASE", "https://api.groq.com/openai"):
            result = agent_server.call_groq(any_agent, "hello", "llama-3.1-8b-instant", api_key="gsk_demo")

        self.assertEqual("groq-fallback-ok", result)
        called_urls = [args[0].full_url for args, _ in mocked_urlopen.call_args_list]
        self.assertEqual(
            [
                "https://api.groq.com/openai/v1/chat/completions",
                "https://api.groq.com/v1/chat/completions",
            ],
            called_urls,
        )

    def test_get_cloud_model_options(self):
        config = {
            "vendors": [
                {
                    "id": "gemini",
                    "name": "Google Gemini",
                    "models": [{"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"}],
                }
            ]
        }
        options = get_cloud_model_options(config)
        self.assertEqual("gemini-1.5-flash", options[0]["id"])
        self.assertEqual("gemini", options[0]["vendor"])

    def test_resolve_cloud_model_credentials_uses_encrypted_config_key(self):
        encrypted = _encrypt_api_key("demo-key", "secret-123")
        self.temp_config.write_text(
            json.dumps(
                {
                    "vendors": [
                        {
                            "id": "gemini",
                            "models": [{"id": "gemini-1.5-flash", "api_key_encrypted": encrypted}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with patch.object(agent_server, "CLOUD_PROVIDERS_CONFIG_PATH", self.temp_config), patch.object(
            agent_server, "API_KEY_ENCRYPTION_SECRET", "secret-123"
        ):
            vendor, model, key = resolve_cloud_model_credentials("gemini-1.5-flash")
        self.assertEqual("gemini", vendor)
        self.assertEqual("gemini-1.5-flash", model)
        self.assertEqual("demo-key", key)

    def test_resolve_cloud_model_credentials_uses_config_secret_without_env(self):
        encrypted = _encrypt_api_key("demo-key", "secret-from-config")
        self.temp_config.write_text(
            json.dumps(
                {
                    "api_key_encryption_secret": "secret-from-config",
                    "vendors": [
                        {
                            "id": "gemini",
                            "models": [{"id": "gemini-1.5-flash", "api_key_encrypted": encrypted}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(agent_server, "CLOUD_PROVIDERS_CONFIG_PATH", self.temp_config), patch.object(
            agent_server, "API_KEY_ENCRYPTION_SECRET", ""
        ):
            vendor, model, key = resolve_cloud_model_credentials("gemini-1.5-flash")
        self.assertEqual("gemini", vendor)
        self.assertEqual("gemini-1.5-flash", model)
        self.assertEqual("demo-key", key)

    def test_resolve_cloud_model_credentials_normalizes_gork_vendor_alias(self):
        encrypted = _encrypt_api_key("demo-key", "secret-from-config")
        self.temp_config.write_text(
            json.dumps(
                {
                    "api_key_encryption_secret": "secret-from-config",
                    "vendors": [
                        {
                            "id": "gork",
                            "models": [{"id": "grok-2", "api_key_encrypted": encrypted}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(agent_server, "CLOUD_PROVIDERS_CONFIG_PATH", self.temp_config), patch.object(
            agent_server, "API_KEY_ENCRYPTION_SECRET", ""
        ):
            vendor, model, key = resolve_cloud_model_credentials("grok-2")
        self.assertEqual("grok", vendor)
        self.assertEqual("grok-2", model)
        self.assertEqual("demo-key", key)

    def test_resolve_cloud_model_credentials_requires_secret_source(self):
        encrypted = _encrypt_api_key("demo-key", "secret-123")
        self.temp_config.write_text(
            json.dumps(
                {
                    "vendors": [
                        {
                            "id": "gemini",
                            "models": [{"id": "gemini-1.5-flash", "api_key_encrypted": encrypted}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with patch.object(agent_server, "CLOUD_PROVIDERS_CONFIG_PATH", self.temp_config), patch.object(
            agent_server, "API_KEY_ENCRYPTION_SECRET", ""
        ):
            with self.assertRaisesRegex(ValueError, "decryption secret is missing"):
                resolve_cloud_model_credentials("gemini-1.5-flash")


if __name__ == "__main__":
    unittest.main()
