from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMClient:
    def __init__(self, timeout: int = 90):
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        attempts: list[tuple[str, str]] = []

        for provider_name, provider_call in (
            ("groq", self._call_groq),
            ("gemini", self._call_gemini),
            ("ollama", self._call_ollama),
        ):
            try:
                return provider_call(prompt)
            except Exception as exc:  # fallback to next provider
                attempts.append((provider_name, str(exc)))

        details = "; ".join(f"{name}: {message}" for name, message in attempts)
        raise RuntimeError(f"All LLM providers failed ({details})")

    def _call_groq(self, prompt: str) -> str:
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        api_url = os.environ.get("GROQ_API_URL", "https://api.groq.com/openai/v1")
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            f"{api_url.rstrip('/')}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        raw = self._read_json(request)
        content = (
            raw.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(raw, dict)
            else ""
        )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned empty content")
        return content.strip()

    def _call_gemini(self, prompt: str) -> str:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        request = urllib.request.Request(
            (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                f"?key={api_key}"
            ),
            data=json.dumps(
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._read_json(request)
        candidates = raw.get("candidates", []) if isinstance(raw, dict) else []
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                content = parts[0].get("text", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Gemini returned empty content")
        return content.strip()

    def _call_ollama(self, prompt: str) -> str:
        api_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")

        body = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            f"{api_url.rstrip('/')}/api/chat",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._read_json(request)
        content = raw.get("message", {}).get("content", "") if isinstance(raw, dict) else ""
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned empty content")
        return content.strip()

    def _read_json(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc
