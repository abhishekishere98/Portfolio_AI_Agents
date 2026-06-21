import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from document_ingestion import DocumentIngestionError, ingest_document_payload
from prd_pipeline import PipelineOptions, run_prd_pipeline


ROOT = Path(__file__).resolve().parent
AGENTS = json.loads((ROOT / "agents.json").read_text(encoding="utf-8"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
API_KEY_ENCRYPTION_SECRET = os.environ.get("API_KEY_ENCRYPTION_SECRET", "")
PORT = int(os.environ.get("AGENT_PORT", "8787"))
PRD_PIPELINE_AGENTS = {"prd_analyst", "prd_reviewer", "test_designer", "automation_designer"}


def fallback_response(agent, user_input):
    name = agent["name"]
    role = agent["role"]
    return f"""# {name}

Model server was not reachable, so this is the deterministic fallback.

Role: {role}

Input received:
{user_input}

Suggested output structure:
1. Clarify the user's goal and target audience.
2. Extract concrete tools, workflows, and measurable outcomes.
3. Produce portfolio-ready copy with sections, bullets, and next actions.
4. Add a demo idea that can be shown publicly without exposing private data.

To enable real model output:
1. Install Ollama.
2. Run: ollama pull {OLLAMA_MODEL}
3. Start this server again with: python agent_server.py
"""


def call_ollama(agent, user_input):
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{agent['prompt']}\n\n"
                    "Be specific, structured, and practical. Avoid generic motivational text."
                ),
            },
            {"role": "user", "content": user_input},
        ],
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("message", {}).get("content", "").strip()


def _derive_encryption_key(secret: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 200000, dklen=32)


def decrypt_api_key(encrypted_value: str, secret: str) -> str:
    if not secret:
        raise ValueError("API_KEY_ENCRYPTION_SECRET is not configured on the backend")
    token = (encrypted_value or "").strip()
    if not token:
        raise ValueError("encrypted_cloud_api_key is empty")

    try:
        payload = base64.urlsafe_b64decode(token.encode("utf-8"))
    except Exception as exc:
        raise ValueError("encrypted_cloud_api_key is not valid base64") from exc

    if len(payload) < 49:
        raise ValueError("encrypted_cloud_api_key payload is invalid")

    salt = payload[:16]
    nonce = payload[16:32]
    ciphertext = payload[32:-32]
    provided_mac = payload[-32:]
    key = _derive_encryption_key(secret, salt)
    expected_mac = hmac.new(key, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_mac, expected_mac):
        raise ValueError("encrypted_cloud_api_key failed integrity validation")

    plaintext = bytes(
        byte ^ key[index % len(key)] ^ nonce[index % len(nonce)]
        for index, byte in enumerate(ciphertext)
    )
    result = plaintext.decode("utf-8").strip()
    if not result:
        raise ValueError("decrypted cloud API key is empty")
    return result


def call_gemini(agent, user_input, model, api_key=None):
    resolved_api_key = (api_key or GEMINI_API_KEY).strip()
    if not resolved_api_key:
        raise ValueError("GEMINI_API_KEY is not configured on the backend")

    instruction = (
        f"{agent['prompt']}\n\n"
        "Be specific, structured, and practical. Avoid generic motivational text."
    )
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"System instruction:\n{instruction}\n\n"
                            f"User request:\n{user_input}"
                        )
                    }
                ]
            }
        ]
    }
    request = urllib.request.Request(
        (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={resolved_api_key}"
        ),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        payload = json.loads(response.read().decode("utf-8"))

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


class AgentHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.set_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/agents":
            self.send_json(
                {
                    "agents": [
                        {"id": key, "name": value["name"], "role": value["role"]}
                        for key, value in AGENTS.items()
                    ]
                }
            )
            return

        self.send_response(404)
        self.set_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/prd/pipeline":
            self.handle_prd_pipeline()
            return

        if self.path != "/api/agents/run":
            self.send_response(404)
            self.set_cors_headers()
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            agent_id = payload.get("agent")
            user_input = (payload.get("input") or "").strip()
            provider = (payload.get("provider") or "local").strip().lower()
            cloud_vendor = (payload.get("cloud_vendor") or "gemini").strip().lower()
            cloud_model = (payload.get("cloud_model") or GEMINI_MODEL).strip()
            encrypted_cloud_api_key = (payload.get("encrypted_cloud_api_key") or "").strip()
            if agent_id not in AGENTS:
                self.send_json({"error": "Unknown agent"}, status=400)
                return
            if not user_input:
                self.send_json({"error": "Missing input"}, status=400)
                return
            if provider not in {"local", "cloud"}:
                self.send_json({"error": "provider must be local or cloud"}, status=400)
                return
            if provider == "cloud" and cloud_vendor != "gemini":
                self.send_json({"error": "cloud_vendor must be gemini"}, status=400)
                return

            agent = AGENTS[agent_id]
            try:
                if provider == "cloud":
                    decrypted_key = None
                    if encrypted_cloud_api_key:
                        decrypted_key = decrypt_api_key(encrypted_cloud_api_key, API_KEY_ENCRYPTION_SECRET)
                    output = call_gemini(agent, user_input, cloud_model, api_key=decrypted_key)
                    model = f"Gemini / {cloud_model}"
                else:
                    output = call_ollama(agent, user_input)
                    model = f"Ollama / {OLLAMA_MODEL}"
            # except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            #     output = fallback_response(agent, user_input)
            #     model = "Fallback mode"
            except Exception as e:
                output = f"MODEL ERROR:\n\n{str(e)}"
                model = "Error"

            self.send_json({"agent": agent_id, "model": model, "output": output})
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_prd_pipeline(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            prd_text = (payload.get("prd_text") or "").strip()
            ingestion_metadata = None
            if not prd_text:
                ingested = ingest_document_payload(payload)
                prd_text = ingested.text
                ingestion_metadata = ingested.metadata
            framework = (payload.get("automation_framework") or "playwright").strip().lower()
            use_llm = bool(payload.get("use_llm", True))
            selected_agents_raw = payload.get("selected_agents")
            selected_agents = []
            if isinstance(selected_agents_raw, list):
                selected_agents = [str(agent).strip() for agent in selected_agents_raw if str(agent).strip()]

            if not prd_text:
                self.send_json({"error": {"code": "empty_document", "message": "Document content is empty"}}, status=400)
                return
            if framework not in {"playwright", "selenium"}:
                self.send_json({"error": "automation_framework must be playwright or selenium"}, status=400)
                return
            if selected_agents:
                invalid_agents = sorted(set(selected_agents) - PRD_PIPELINE_AGENTS)
                if invalid_agents:
                    self.send_json({"error": f"selected_agents contains unsupported values: {', '.join(invalid_agents)}"}, status=400)
                    return

            result = run_prd_pipeline(
                prd_text,
                PipelineOptions(
                    automation_framework=framework,
                    model=OLLAMA_MODEL,
                    ollama_url=OLLAMA_URL,
                    use_llm=use_llm,
                ),
            )
            if selected_agents:
                result["selected_agents"] = selected_agents
            if ingestion_metadata:
                result["document"] = {
                    "source_type": "uploaded_file",
                    "normalized": True,
                    "metadata": ingestion_metadata,
                }
            else:
                result["document"] = {
                    "source_type": "text",
                    "normalized": True,
                    "metadata": {
                        "filename": None,
                        "extension": None,
                        "page_count": None,
                        "word_count": len(prd_text.split()),
                        "character_count": len(prd_text),
                    },
                }
            self.send_json(result)
        except DocumentIngestionError as exc:
            self.send_json(exc.to_dict(), status=400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("localhost", PORT), AgentHandler)
    print(f"Agent server running at http://localhost:{PORT}")
    print(f"Ollama endpoint: {OLLAMA_URL} | model: {OLLAMA_MODEL}")
    server.serve_forever()
