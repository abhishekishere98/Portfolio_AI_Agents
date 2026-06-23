import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from document_ingestion import DocumentIngestionError, ingest_document_payload
from prd_excel_export import build_prd_excel_bytes
from prd_pipeline import PipelineExecutionError, PipelineOptions, run_prd_pipeline


ROOT = Path(__file__).resolve().parent
AGENT_REGISTRY_PATH = ROOT / "agents.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com")
GEMINI_API_VERSION = os.environ.get("GEMINI_API_VERSION", "v1")
GEMINI_FALLBACK_API_VERSION = os.environ.get("GEMINI_FALLBACK_API_VERSION", "v1beta")
GEMINI_MODEL_ALIASES = {
    "gemini-1.5-flash": "gemini-2.5-flash-lite",
    "gemini-1.5-pro": "gemini-2.5-pro",
}
GROK_API_BASE = os.environ.get("GROK_API_BASE", "https://api.x.ai")
GROK_API_VERSION = os.environ.get("GROK_API_VERSION", "v1")
GROK_TIMEOUT_SECONDS = int(os.environ.get("GROK_TIMEOUT_SECONDS", "900"))
GROQ_API_BASE = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai")
GROQ_API_VERSION = os.environ.get("GROQ_API_VERSION", "v1")
GROQ_TIMEOUT_SECONDS = int(os.environ.get("GROQ_TIMEOUT_SECONDS", "900"))

GROK_MODEL_ALIASES = {
    "grok-2": "grok-3-mini",
}

API_KEY_ENCRYPTION_SECRET = os.environ.get("API_KEY_ENCRYPTION_SECRET", "")
CLOUD_PROVIDERS_CONFIG_PATH = ROOT / os.environ.get("CLOUD_PROVIDERS_CONFIG", "cloud_providers.json")
PORT = int(os.environ.get("PORT", os.environ.get("AGENT_PORT", "8787")))

CONFIG_SECRET_FIELDS = (
    "api_key_encryption_secret",
    "encryption_secret",
    "decryption_secret",
)
EXPORT_TTL_SECONDS = int(os.environ.get("EXPORT_TTL_SECONDS", "1800"))
EXPORT_CACHE: dict[str, dict[str, object]] = {}


def load_agent_registry() -> dict:
    """Load centralized UI/backend agent registry.

    The registry is the single source of truth for:
    - grouped agent navigation metadata,
    - agent execution prompts/roles,
    - provider visibility controls used by UI runtime options.
    """

    payload = json.loads(AGENT_REGISTRY_PATH.read_text(encoding="utf-8"))
    categories = payload.get("categories")
    agents = payload.get("agents")
    providers = payload.get("providers")
    if not isinstance(categories, list) or not isinstance(agents, list) or not isinstance(providers, dict):
        raise ValueError("agents.json must define categories(list), agents(list), and providers(object)")
    return payload


def _iter_enabled_agents(registry: dict) -> list[dict]:
    return [agent for agent in registry.get("agents", []) if isinstance(agent, dict) and agent.get("enabled", True)]


def _build_execution_agent_map(registry: dict) -> dict[str, dict]:
    """Create execution-ready mapping keyed by agent id for non-pipeline agents."""

    execution_map: dict[str, dict] = {}
    for agent in _iter_enabled_agents(registry):
        agent_id = str(agent.get("id") or "").strip()
        if not agent_id or agent.get("is_pipeline"):
            continue
        execution_map[agent_id] = {
            "name": str(agent.get("name") or agent_id),
            "role": str(agent.get("role") or "General assistant"),
            "prompt": str(agent.get("prompt") or "Provide concise, structured output."),
            "executionProvider": str(agent.get("executionProvider") or "cloud"),
        }
    return execution_map


def _build_grouped_agents(registry: dict) -> list[dict]:
    """Build category-grouped agents consumed by the frontend agent navigation."""

    enabled_agents = _iter_enabled_agents(registry)
    by_category: dict[str, list[dict]] = {}
    for agent in enabled_agents:
        category = str(agent.get("category") or "other")
        by_category.setdefault(category, []).append(
            {
                "id": agent.get("id"),
                "name": agent.get("name"),
                "short": agent.get("short") or "",
                "description": agent.get("description") or "",
                "category": category,
                "executionProvider": agent.get("executionProvider") or "cloud",
                "icon": agent.get("icon") or "",
                "is_pipeline": bool(agent.get("is_pipeline", False)),
                "capabilities": {
                    "supportsExcelExport": bool(agent.get("supportsExcelExport", False)),
                },
            }
        )

    grouped: list[dict] = []
    for category in registry.get("categories", []):
        category_id = str(category.get("id") or "")
        grouped.append(
            {
                "id": category_id,
                "name": category.get("name") or category_id.title(),
                "agents": by_category.get(category_id, []),
            }
        )
    return grouped


AGENT_REGISTRY = load_agent_registry()
AGENTS = _build_execution_agent_map(AGENT_REGISTRY)


def _get_provider_options(cloud_models: list[dict]) -> dict[str, dict]:
    """Merge static provider registry metadata with dynamic cloud model list.

    TODO: re-enable `local` in UI by flipping `enabled` in `agents.json` once
    local Ollama execution is part of the active product roadmap again.
    """

    providers = AGENT_REGISTRY.get("providers", {})
    merged: dict[str, dict] = {}
    for provider_id, defaults in {
        "local": {"id": "local", "label": "Local (Ollama)", "enabled": False},
        "cloud": {"id": "cloud", "label": "Cloud", "enabled": True},
        "openai": {"id": "openai", "label": "OpenAI", "enabled": False},
        "gemini": {"id": "gemini", "label": "Gemini", "enabled": False},
        "grok": {"id": "grok", "label": "Grok", "enabled": False},
    }.items():
        merged[provider_id] = dict(providers.get(provider_id, defaults))

    merged["cloud"]["models"] = cloud_models
    merged["gemini"]["models"] = cloud_models
    return merged


def _is_supported_provider(provider: str) -> bool:
    return provider in {"local", "cloud", "openai", "gemini", "grok"}


def _normalize_provider_for_execution(provider: str) -> str:
    """Map UI-facing provider ids to currently supported execution backends.

    OpenAI/Grok are exposed via provider abstraction in V1 UI, but execution is
    currently routed through cloud model credentials (Gemini-backed) until
    dedicated transports are added.
    """

    normalized = (provider or "").strip().lower()
    return "local" if normalized == "local" else "cloud"


def _normalize_cloud_vendor(vendor: str) -> str:
    """Normalize cloud-vendor aliases from UI/config into canonical ids."""

    normalized = (vendor or "").strip().lower()
    if normalized == "gork":
        return "grok"
    return normalized


def _cleanup_expired_exports() -> None:
    """Remove stale in-memory export artifacts to keep memory usage bounded."""

    now = time.time()
    expired = [token for token, item in EXPORT_CACHE.items() if float(item.get("expires_at", 0)) <= now]
    for token in expired:
        EXPORT_CACHE.pop(token, None)


def _store_export_artifact(filename: str, content: bytes) -> str:
    """Store generated export bytes and return a short download token.

    Input: artifact filename and binary content.
    Output: opaque token consumed by `/api/exports/<token>`.
    """

    _cleanup_expired_exports()
    token = secrets.token_urlsafe(16)
    EXPORT_CACHE[token] = {
        "filename": filename,
        "content": content,
        "expires_at": time.time() + EXPORT_TTL_SECONDS,
    }
    return token


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


def load_cloud_providers_config() -> dict:
    if not CLOUD_PROVIDERS_CONFIG_PATH.exists():
        return {"vendors": []}
    try:
        config = json.loads(CLOUD_PROVIDERS_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("cloud providers config is not valid JSON") from exc
    vendors = config.get("vendors")
    if not isinstance(vendors, list):
        raise ValueError("cloud providers config must include a vendors list")
    return {
        "vendors": vendors,
        "api_key_encryption_secret": config.get("api_key_encryption_secret"),
        "encryption_secret": config.get("encryption_secret"),
        "decryption_secret": config.get("decryption_secret"),
    }


def _read_secret_from_config(source: dict) -> str:
    for field in CONFIG_SECRET_FIELDS:
        value = str(source.get(field) or "").strip()
        if value:
            return value
    return ""


def _resolve_decryption_secret(config: dict, vendor: dict, model: dict) -> str:
    model_secret = _read_secret_from_config(model)
    if model_secret:
        return model_secret
    vendor_secret = _read_secret_from_config(vendor)
    if vendor_secret:
        return vendor_secret
    config_secret = _read_secret_from_config(config)
    if config_secret:
        return config_secret
    return API_KEY_ENCRYPTION_SECRET


def get_cloud_model_options(config: dict) -> list[dict]:
    options: list[dict] = []
    for vendor in config.get("vendors", []):
        vendor_id = str(vendor.get("id") or "").strip()
        vendor_name = str(vendor.get("name") or vendor_id).strip()
        models = vendor.get("models") or []
        if not vendor_id or not isinstance(models, list):
            continue
        for model in models:
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            options.append(
                {
                    "id": model_id,
                    "name": str(model.get("name") or model_id),
                    "vendor": vendor_id,
                    "vendor_name": vendor_name,
                }
            )
    return options


def resolve_cloud_model_credentials(model_id: str) -> tuple[str, str, str]:
    config = load_cloud_providers_config()
    for vendor in config.get("vendors", []):
        vendor_id = _normalize_cloud_vendor(str(vendor.get("id") or ""))
        for model in vendor.get("models", []):
            config_model_id = str(model.get("id") or "").strip()
            if config_model_id != model_id:
                continue
            encrypted_key = str(model.get("api_key_encrypted") or "").strip()
            if not encrypted_key:
                raise ValueError(f"Encrypted API key is missing for cloud model: {model_id}")
            secret = _resolve_decryption_secret(config, vendor, model)
            if not secret:
                raise ValueError(
                    "API key decryption secret is missing. Set one of "
                    "[api_key_encryption_secret, encryption_secret, decryption_secret] "
                    "in cloud_providers.json (model/vendor/root), or set API_KEY_ENCRYPTION_SECRET."
                )
            decrypted_key = decrypt_api_key(encrypted_key, secret)
            return vendor_id, config_model_id, decrypted_key
    raise ValueError(f"Unknown cloud model: {model_id}")


def _resolve_gemini_model(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return GEMINI_MODEL
    return GEMINI_MODEL_ALIASES.get(normalized, normalized)


def call_gemini(agent, user_input, model, api_key=None):
    resolved_api_key = (api_key or GEMINI_API_KEY).strip()
    if not resolved_api_key:
        raise ValueError("GEMINI_API_KEY is not configured on the backend")

    resolved_model = _resolve_gemini_model(model)
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
    endpoint_versions = [GEMINI_API_VERSION]
    if GEMINI_FALLBACK_API_VERSION and GEMINI_FALLBACK_API_VERSION not in endpoint_versions:
        endpoint_versions.append(GEMINI_FALLBACK_API_VERSION)

    payload = None
    last_error: Exception | None = None
    for version in endpoint_versions:
        request = urllib.request.Request(
            (
                f"{GEMINI_API_BASE.rstrip('/')}/{version}/models/{resolved_model}:generateContent"
                f"?key={resolved_api_key}"
            ),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404 and version != endpoint_versions[-1]:
                continue
            raise

    if payload is None and last_error is not None:
        raise last_error
    if payload is None:
        raise ValueError("Gemini request failed before any response payload was received")

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


def call_grok(agent, user_input, model, api_key: str):
    """Call Grok using xAI's OpenAI-compatible chat completions API."""

    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise ValueError("Cloud model API key is missing for Grok provider")

    # Compatibility guard: `gsk_` keys are Groq keys, not xAI keys.
    # Route them to Groq's OpenAI-compatible endpoint so existing configs work.
    if resolved_api_key.startswith("gsk_"):
        return call_groq(agent, user_input, model, api_key=resolved_api_key)

    resolved_model = GROK_MODEL_ALIASES.get(str(model or "").strip(), str(model or "").strip())
    if not resolved_model:
        raise ValueError("Grok model id is required")

    instruction = (
        f"{agent['prompt']}\n\n"
        "Be specific, structured, and practical. Avoid generic motivational text."
    )
    body = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_input},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {resolved_api_key}",
    }

    request = urllib.request.Request(
        f"{GROK_API_BASE.rstrip('/')}/{GROK_API_VERSION}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=GROK_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        text = str(content or "").strip()
        if text:
            return text
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="ignore")
        if exc.code != 400:
            message = raw_error[:500].strip() or str(exc)
            raise ValueError(f"Grok request failed: HTTP {exc.code}: {message}") from exc

        responses_request = urllib.request.Request(
            f"{GROK_API_BASE.rstrip('/')}/{GROK_API_VERSION}/responses",
            data=json.dumps(
                {
                    "model": resolved_model,
                    "instructions": instruction,
                    "input": user_input,
                }
            ).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(responses_request, timeout=GROK_TIMEOUT_SECONDS) as response:
                responses_payload = json.loads(response.read().decode("utf-8"))
            output_text = str(responses_payload.get("output_text") or "").strip()
            if output_text:
                return output_text
            message = json.dumps(responses_payload)[:500]
            raise ValueError(f"Grok returned an empty response body: {message}")
        except urllib.error.HTTPError as fallback_exc:
            fallback_body = fallback_exc.read().decode("utf-8", errors="ignore")
            message = fallback_body[:500].strip() or raw_error[:500].strip() or str(fallback_exc)
            raise ValueError(f"Grok request failed: HTTP {fallback_exc.code}: {message}") from fallback_exc

    raise ValueError("Grok returned an empty response")


def call_groq(agent, user_input, model, api_key: str):
    """Call Groq using OpenAI-compatible chat completions endpoint."""

    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise ValueError("Cloud model API key is missing for Groq provider")

    instruction = (
        f"{agent['prompt']}\n\n"
        "Be specific, structured, and practical. Avoid generic motivational text."
    )
    body = {
        "model": str(model or "").strip(),
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_input},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {resolved_api_key}",
        "User-Agent": "AIAgents-Server/1.0",
    }

    def _request_chat(url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=GROQ_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    primary_url = f"{GROQ_API_BASE.rstrip('/')}/{GROQ_API_VERSION}/chat/completions"

    try:
        payload = _request_chat(primary_url)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="ignore")
        # Some Groq accounts/environments can return Cloudflare 1010 on one path.
        # Retry the non-OpenAI-prefixed endpoint before surfacing an error.
        if exc.code == 403 and "1010" in raw_body:
            fallback_base = GROQ_API_BASE.rstrip("/")
            if fallback_base.endswith("/openai"):
                fallback_base = fallback_base[: -len("/openai")]
            fallback_url = f"{fallback_base}/{GROQ_API_VERSION}/chat/completions"
            try:
                payload = _request_chat(fallback_url)
            except urllib.error.HTTPError as fallback_exc:
                fallback_body = fallback_exc.read().decode("utf-8", errors="ignore")
                message = fallback_body[:500].strip() or raw_body[:500].strip() or str(fallback_exc)
                raise ValueError(f"Groq request failed: HTTP {fallback_exc.code}: {message}") from fallback_exc
        else:
            message = raw_body[:500].strip() or str(exc)
            raise ValueError(f"Groq request failed: HTTP {exc.code}: {message}") from exc

    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    text = str(content or "").strip()
    if not text:
        raise ValueError("Groq returned an empty response")
    return text


class AgentHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.set_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/exports/"):
            token = self.path.split("/api/exports/", 1)[1].strip()
            _cleanup_expired_exports()
            artifact = EXPORT_CACHE.get(token)
            if not artifact:
                self.send_json({"error": "Export file not found or expired"}, status=404)
                return

            filename = str(artifact.get("filename") or "PRD_PRD_Analysis.xlsx")
            content = artifact.get("content")
            if not isinstance(content, (bytes, bytearray)):
                self.send_json({"error": "Export content is unavailable"}, status=404)
                return
            payload = bytes(content)

            self.send_response(200)
            self.set_cors_headers()
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path == "/api/agents":
            grouped_agents = _build_grouped_agents(AGENT_REGISTRY)
            flat_agents = [
                {
                    "id": agent["id"],
                    "name": agent["name"],
                    "role": AGENTS.get(agent["id"], {}).get("role", "Run PRD workflow from text or uploaded files."),
                    "category": agent.get("category"),
                    "description": agent.get("description", ""),
                    "short": agent.get("short", ""),
                    "executionProvider": agent.get("executionProvider", "cloud"),
                    "is_pipeline": bool(agent.get("is_pipeline", False)),
                    "capabilities": {
                        "supportsExcelExport": bool(agent.get("supportsExcelExport", False)),
                    },
                }
                for group in grouped_agents
                for agent in group.get("agents", [])
            ]
            self.send_json(
                {
                    "agents": flat_agents,
                    "grouped_agents": grouped_agents,
                    "categories": AGENT_REGISTRY.get("categories", []),
                }
            )
            return

        if self.path == "/api/runtime/options":
            try:
                config = load_cloud_providers_config()
                cloud_models = get_cloud_model_options(config)
                self.send_json(
                    {
                        "providers": _get_provider_options(cloud_models)
                    }
                )
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=500)
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
            provider = (payload.get("provider") or "cloud").strip().lower()
            cloud_model = (payload.get("cloud_model") or GEMINI_MODEL).strip()
            requested_cloud_vendor = _normalize_cloud_vendor(payload.get("cloud_vendor") or provider)
            if agent_id != "prd_pipeline" and agent_id not in AGENTS:
                self.send_json({"error": "Unknown agent"}, status=400)
                return
            if not user_input and agent_id != "prd_pipeline":
                self.send_json({"error": "Missing input"}, status=400)
                return
            if not _is_supported_provider(provider):
                self.send_json({"error": "provider must be one of local, cloud, openai, gemini, grok"}, status=400)
                return
            execution_provider = _normalize_provider_for_execution(provider)
            if agent_id == "prd_pipeline":
                self.handle_prd_pipeline(payload, provider=execution_provider, cloud_model=cloud_model)
                return

            agent = AGENTS[agent_id]
            try:
                if execution_provider != "local":
                    cloud_vendor, resolved_model, decrypted_key = resolve_cloud_model_credentials(cloud_model)
                    requested_vendor = _normalize_cloud_vendor(requested_cloud_vendor or provider or "gemini")
                    if requested_vendor not in {"cloud", "gemini", "openai", "grok", cloud_vendor}:
                        self.send_json(
                            {
                                "error": {
                                    "code": "unsupported_cloud_vendor",
                                    "message": f"Unsupported cloud vendor: {requested_vendor}",
                                }
                            },
                            status=400,
                        )
                        return
                    if cloud_vendor == "grok":
                        output = call_grok(agent, user_input, resolved_model, api_key=decrypted_key)
                        model = f"Grok / {resolved_model}"
                    else:
                        output = call_gemini(agent, user_input, resolved_model, api_key=decrypted_key)
                        model = f"Gemini / {resolved_model}"
                else:
                    output = call_ollama(agent, user_input)
                    model = f"Ollama / {OLLAMA_MODEL}"
            # except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            #     output = fallback_response(agent, user_input)
            #     model = "Fallback mode"
            except ValueError as exc:
                self.send_json({"error": {"code": "provider_validation_failed", "message": str(exc)}}, status=400)
                return
            except Exception as exc:
                self.send_json({"error": {"code": "model_call_failed", "message": str(exc)}}, status=502)
                return

            self.send_json({"agent": agent_id, "model": model, "output": output})
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_prd_pipeline(self, payload: dict | None = None, provider: str = "local", cloud_model: str = GEMINI_MODEL):
        """Handle PRD pipeline execution requests.

        WHY this exists:
        The API route must centralize payload normalization (text vs uploaded
        document), provider credential resolution, and error contract mapping so
        frontend diagnostics remain actionable.
        """

        try:
            if payload is None:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            prd_text = (payload.get("prd_text") or "").strip()
            ingestion_metadata = None
            if not prd_text:
                ingested = ingest_document_payload(payload)
                prd_text = ingested.text
                ingestion_metadata = ingested.metadata
            if not prd_text:
                self.send_json({"error": {"code": "empty_document", "message": "Document content is empty"}}, status=400)
                return
            if not _is_supported_provider(provider):
                self.send_json({"error": "provider must be one of local, cloud, openai, gemini, grok"}, status=400)
                return
            execution_provider = _normalize_provider_for_execution(provider)

            cloud_api_key = None
            if execution_provider != "local":
                cloud_vendor, resolved_model, cloud_api_key = resolve_cloud_model_credentials(cloud_model)
                cloud_model = resolved_model

            result = run_prd_pipeline(
                prd_text,
                PipelineOptions(
                    automation_framework="playwright",
                    model=OLLAMA_MODEL,
                    ollama_url=OLLAMA_URL,
                    use_llm=True,
                    provider=execution_provider,
                    cloud_model=cloud_model,
                    cloud_api_key=cloud_api_key,
                ),
            )
            result["provider"] = provider
            if provider == "cloud":
                result["cloud_model"] = cloud_model
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

            # Generate Excel workbook artifact from the final pipeline payload.
            # Input: complete PRD pipeline result dict.
            # Output: `artifacts.excel` metadata with direct download URL.
            excel_filename, excel_bytes = build_prd_excel_bytes(result)
            export_token = _store_export_artifact(excel_filename, excel_bytes)
            result["artifacts"] = {
                "excel": {
                    "filename": excel_filename,
                    "download_url": f"/api/exports/{export_token}",
                }
            }

            self.send_json(result)
        except DocumentIngestionError as exc:
            self.send_json(exc.to_dict(), status=400)
        except PipelineExecutionError as exc:
            self.send_json(
                {
                    "error": {
                        "code": "pipeline_execution_failed",
                        "message": str(exc),
                    }
                },
                status=502,
            )
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
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AgentHandler)
    # print(f"Agent server running at http://localhost:{PORT}")
    # print(f"Ollama endpoint: {OLLAMA_URL} | model: {OLLAMA_MODEL}")
    server.serve_forever()
