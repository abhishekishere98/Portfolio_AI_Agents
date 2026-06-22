import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator


DEFAULT_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_REVIEW_LOOPS = 2
OLLAMA_CHAT_TIMEOUT_SECONDS = 300
GEMINI_CHAT_TIMEOUT_SECONDS = 120
MAX_AGENT_PAYLOAD_CHARS = int(os.environ.get("PRD_AGENT_MAX_INPUT_CHARS", "24000"))
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com")
GEMINI_API_VERSION = os.environ.get("GEMINI_API_VERSION", "v1")
GEMINI_FALLBACK_API_VERSION = os.environ.get("GEMINI_FALLBACK_API_VERSION", "v1beta")
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_MODEL_ALIASES = {
    "gemini-1.5-flash": "gemini-2.5-flash-lite",
    "gemini-1.5-pro": "gemini-2.5-pro",
}

logger = logging.getLogger(__name__)
NON_BLOCKING_KEYWORDS = [
    "toast",
    "success message",
    "button",
    "icon",
    "currency",
    "format",
    "image size",
    "image resolution",
    "notification wording",
]

AGENT_PROMPTS = {
    "prd_analyst": """You are Agent 1: PRD Analyst.

You will receive PRD text, retrieval context, and quality-gate metadata.

Your goals:
1) Decide whether this is a software PRD/enhancement document.
2) If not, return status REJECTED and reason exactly:
   \"Document is not a software product requirements document\".
3) If valid, extract implementation-ready requirements.

Critical rules:
- Every epic must map to explicit PRD requirements.
- Every story must map to explicit PRD requirements.
- Do NOT invent generic epics/stories.
- Forbidden generic epic/story titles include:
  Core User Workflow, Complete primary action, Handle exceptions safely,
  Main Feature, Primary Action, Error Handling.
- Preserve business terminology from PRD.
- Return JSON only (no markdown, no code fences).

Required JSON shape:
{
  "status": "VALID_PRD" | "REJECTED",
  "product_name": "string",
  "business_goal": "string",
  "personas": [{"name":"string","goal":"string"}],
  "epics": [
    {
      "id": "EPIC-1",
      "title": "string",
      "description": "string",
      "source_requirement": "exact requirement phrase from PRD",
      "target_persona": "string",
      "user_stories": [
        {
          "id": "US-1.1",
          "title": "string",
          "story": "As a ..., I want ..., so that ...",
          "priority": "High|Medium|Low",
          "acceptance_criteria": ["Given/When/Then..."]
        }
      ]
    }
  ],
  "assumptions": ["..."],
  "risks": ["..."],
  "reason": "optional rejection reason"
}""",
    "prd_reviewer": """You are Agent 2: Senior QA Requirement Reviewer.

Input:
- Original PRD text
- Agent 1 structured output

Your responsibility is to determine whether the PRD is sufficiently complete
for development, testing and automation planning.

Important:

DO NOT raise findings for:

- UI styling
- Button appearance
- Icon selection
- Toast wording
- Currency formatting
- Image dimensions
- Minor UX implementation choices

Only raise BLOCKERS when:

- Business workflow is missing
- System behavior is missing
- Acceptance criteria are impossible to test
- Requirements contradict each other
- Multiple materially different implementations are possible

Non-blocking observations should be placed into:

- ambiguous_requirements
- missing_acceptance_criteria
- testability_concerns

Decision Rules:

REWORK_REQUIRED:
One or more blockers exist.

APPROVED_WITH_OBSERVATIONS:
No blockers exist but observations exist.

APPROVED:
No blockers and no observations.

Return JSON only.

{
  "decision": "APPROVED|APPROVED_WITH_OBSERVATIONS|REWORK_REQUIRED",

  "blockers": [],

  "missing_requirements": [],

  "ambiguous_requirements": [],

  "missing_acceptance_criteria": [],

  "testability_concerns": []
}""",
    "test_designer": """You are Agent 3: Test Designer.

Input contains approved requirements with epics, stories, and acceptance criteria.

Create executable test design directly from acceptance criteria.
Every acceptance criterion must map to at least one story-level test.

Return JSON only with:
{
  "story_level_tests": [
    {
      "story_id": "US-1.1",
      "title": "string",
      "test_type": "Positive|Negative|Boundary|Contract|Security",
      "priority": "High|Medium|Low",
      "preconditions": "string",
      "steps": "string",
      "expected_result": "string"
    }
  ],
  "epic_level_tests": [
    {
      "epic_id": "EPIC-1",
      "title": "string",
      "priority": "High|Medium|Low",
      "preconditions": "string",
      "steps": "string",
      "expected_result": "string"
    }
  ],
  "traceability_matrix": [
    {
      "epic_id": "EPIC-1",
      "story_id": "US-1.1",
      "coverage": "string"
    }
  ]
}""",
    "automation_designer": """You are Agent 4: Automation Designer.

Input:
- approved PRD structure
- test design
- automation framework (playwright or selenium)

Task:
- Produce automation-ready suites and implementation guidance.
- Do not invent unknown selectors or hidden workflows.

Return JSON only:
{
  "selected_framework": "playwright|selenium",
  "automation_suites": [
    {
      "name": "string",
      "framework": "playwright|selenium",
      "test_type": "e2e|component|integration",
      "steps": ["..."],
      "locator_strategy": "string",
      "alumnium_optional_steps": ["..."]
    }
  ],
  "ci_notes": ["..."],
  "alumnium_guidance": "string"
}""",
}


class PersonaModel(BaseModel):
    name: str
    goal: str


class StoryModel(BaseModel):
    id: str
    title: str
    story: str
    priority: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class EpicModel(BaseModel):
    id: str
    title: str
    description: str
    source_requirement: str
    target_persona: str
    user_stories: list[StoryModel] = Field(default_factory=list)


class Agent1AcceptedModel(BaseModel):
    status: str = "VALID_PRD"
    product_name: str
    business_goal: str
    personas: list[PersonaModel] = Field(default_factory=list)
    epics: list[EpicModel] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class Agent1RejectedModel(BaseModel):
    status: str = "REJECTED"
    reason: str = "Document is not a software product requirements document"


class Agent1ResponseModel(BaseModel):
    status: str
    product_name: str | None = None
    business_goal: str | None = None
    personas: list[PersonaModel] | None = None
    epics: list[EpicModel] | None = None
    assumptions: list[str] | None = None
    risks: list[str] | None = None
    reason: str | None = None


class Agent2ReviewModel(BaseModel):
    decision: str

    blockers: list[str] = Field(default_factory=list)

    missing_requirements: list[str] = Field(default_factory=list)

    ambiguous_requirements: list[str] = Field(default_factory=list)

    missing_acceptance_criteria: list[str] = Field(default_factory=list)

    testability_concerns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_decision_matches_findings(self) -> "Agent2ReviewModel":

        if self.blockers:

            if self.decision != "REWORK_REQUIRED":
                raise ValueError(
                    "decision must be REWORK_REQUIRED when blockers exist"
                )

        else:

            if self.decision not in (
                "APPROVED",
                "APPROVED_WITH_OBSERVATIONS",
            ):
                raise ValueError(
                    "decision must be APPROVED or APPROVED_WITH_OBSERVATIONS when no blockers exist"
                )

        return self


class StoryLevelTestModel(BaseModel):
    story_id: str
    title: str
    test_type: str
    priority: str
    preconditions: str
    steps: str
    expected_result: str


class EpicLevelTestModel(BaseModel):
    epic_id: str
    title: str
    priority: str
    preconditions: str
    steps: str
    expected_result: str


class TraceabilityModel(BaseModel):
    epic_id: str
    story_id: str
    coverage: str


class Agent3TestDesignModel(BaseModel):
    story_level_tests: list[StoryLevelTestModel] = Field(default_factory=list)
    epic_level_tests: list[EpicLevelTestModel] = Field(default_factory=list)
    traceability_matrix: list[TraceabilityModel] = Field(default_factory=list)


class AutomationSuiteModel(BaseModel):
    name: str
    framework: str
    test_type: str
    steps: list[str] = Field(default_factory=list)
    locator_strategy: str
    alumnium_optional_steps: list[str] = Field(default_factory=list)


class Agent4AutomationDesignModel(BaseModel):
    selected_framework: str
    automation_suites: list[AutomationSuiteModel] = Field(default_factory=list)
    ci_notes: list[str] = Field(default_factory=list)
    alumnium_guidance: str


@dataclass
class PipelineOptions:
    """Runtime options for PRD pipeline orchestration.

    This object intentionally keeps transport/provider concerns separate from
    agent prompts so callers can switch providers without touching workflow
    business logic.
    """
    automation_framework: str = "playwright"
    model: str = DEFAULT_MODEL
    ollama_url: str = DEFAULT_OLLAMA_URL
    use_llm: bool = True
    provider: str = "local"
    cloud_model: str = DEFAULT_GEMINI_MODEL
    cloud_api_key: str = ""


class PipelineExecutionError(RuntimeError):
    """Raised when an LLM-backed agent call fails and deterministic fallback is not allowed."""


def _log_event(event: str, **fields: Any) -> None:
    """Emit structured diagnostic logs for provider and validation troubleshooting."""

    detail = " ".join(f"{key}={value!r}" for key, value in fields.items())
    logger.warning("%s %s", event, detail)


def _summarize_text(value: str | None, max_chars: int = 300) -> str:
    """Create a bounded text summary suitable for logs to avoid noisy payload dumps."""

    text = (value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _load_forbidden_generic_titles() -> set[str]:
    """Load known bad generic titles from source prompts for consistency.

    WHY this exists:
    Agent 1 quality checks should reject the exact generic labels that were
    repeatedly seen in degraded outputs.
    """

    source = Path(__file__).read_text(encoding="utf-8")
    labels = set(re.findall(r"- ([A-Za-z][A-Za-z\s]+)", source))
    known = {
        "Core User Workflow",
        "Complete primary action",
        "Handle exceptions safely",
        "Main Feature",
        "Primary Action",
        "Error Handling",
    }
    return {label.strip().lower() for label in labels if label.strip()} | {value.lower() for value in known}


FORBIDDEN_GENERIC_TITLES = _load_forbidden_generic_titles()


def _validate_agent_response(agent_key: str, response: Any, quality_gate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate agent responses against strong stage-specific Pydantic models.

    Input schema:
    - `agent_key`: pipeline stage key
    - `response`: parsed JSON object from provider
    - `quality_gate`: optional gate metrics used by Agent 1

    Output schema:
    - strict dict validated by stage model
    """

    if not isinstance(response, dict):
        _log_event("VALIDATION_RESULT", agent=agent_key, is_dict=False)
        raise PipelineExecutionError(f"Agent '{agent_key}' returned non-object payload: {type(response).__name__}")

    try:
        if agent_key == "prd_analyst":
            payload = _validate_agent1_response(response, quality_gate or {})
        elif agent_key == "prd_reviewer":
            payload = Agent2ReviewModel.model_validate(response).model_dump()
        elif agent_key == "test_designer":
            payload = Agent3TestDesignModel.model_validate(response).model_dump()
        elif agent_key == "automation_designer":
            payload = Agent4AutomationDesignModel.model_validate(response).model_dump()
        else:
            raise PipelineExecutionError(f"Unknown agent key: {agent_key}")
    except ValidationError as exc:
        _log_event("VALIDATION_RESULT", agent=agent_key, is_dict=True, valid=False, error=str(exc))
        raise PipelineExecutionError(f"Agent '{agent_key}' schema validation failed: {exc}") from exc
    except ValueError as exc:
        _log_event("VALIDATION_RESULT", agent=agent_key, is_dict=True, valid=False, error=str(exc))
        raise PipelineExecutionError(f"Agent '{agent_key}' validation failed: {exc}") from exc

    _log_event("VALIDATION_RESULT", agent=agent_key, is_dict=True, valid=True)
    return payload


def _validate_agent1_response(response: dict[str, Any], quality_gate: dict[str, Any]) -> dict[str, Any]:
    """Apply Agent 1 schema validation and anti-generic quality checks.

    This enforces that accepted PRD outputs contain requirement-derived epics and
    stories, and blocks known generic template titles.
    """

    normalized_status = str(response.get("status") or "").strip().upper()
    if normalized_status == "REJECTED":
        rejected = Agent1RejectedModel.model_validate({
            "status": "REJECTED",
            "reason": "Document is not a software product requirements document",
        })
        return rejected.model_dump()

    accepted = Agent1AcceptedModel.model_validate({
        "status": "VALID_PRD",
        "product_name": response.get("product_name"),
        "business_goal": response.get("business_goal"),
        "personas": response.get("personas") or [],
        "epics": response.get("epics") or [],
        "assumptions": response.get("assumptions") or [],
        "risks": response.get("risks") or [],
    })
    result = accepted.model_dump()

    violations = _find_generic_title_violations(result.get("epics") or [])
    if violations:
        return {
            "status": "REJECTED",
            "reason": "Document is not a software product requirements document",
            "rejection_reasons": [
                "Agent 1 generated generic epics/stories not derived from explicit PRD requirements.",
                *violations,
            ],
            "quality_gate": quality_gate,
        }
    return result


def _find_generic_title_violations(epics: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for epic in epics:
        epic_title = str(epic.get("title") or "").strip().lower()
        if epic_title in FORBIDDEN_GENERIC_TITLES:
            violations.append(f"Forbidden generic epic title: {epic.get('title')}")
        for story in epic.get("user_stories") or []:
            story_title = str(story.get("title") or "").strip().lower()
            if story_title in FORBIDDEN_GENERIC_TITLES:
                violations.append(f"Forbidden generic user story title: {story.get('title')}")
    return violations


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 20].rstrip() + "\n\n[TRUNCATED_FOR_MODEL]"


def _prepare_payload_for_llm(payload: dict[str, Any]) -> dict[str, Any]:
    """Bound payload size to avoid provider timeouts and context overflows."""

    serialized = json.dumps(payload, ensure_ascii=False)
    original_size = len(serialized)
    if original_size <= MAX_AGENT_PAYLOAD_CHARS:
        _log_event("AGENT_PAYLOAD_SIZE", size=original_size, max_size=MAX_AGENT_PAYLOAD_CHARS, truncated=False)
        return payload

    result = dict(payload)
    prd_extract = str(result.get("prd_extract") or "")
    if prd_extract:
        result["prd_extract"] = _truncate_text(prd_extract, max(2000, int(MAX_AGENT_PAYLOAD_CHARS * 0.55)))

    retrieval_context = result.get("retrieval_context")
    if isinstance(retrieval_context, dict):
        trimmed_context = dict(retrieval_context)
        top_chunks = trimmed_context.get("top_chunks")
        if isinstance(top_chunks, list):
            trimmed_context["top_chunks"] = [str(chunk)[:900] for chunk in top_chunks[:5]]
        chunks = trimmed_context.get("chunks")
        if isinstance(chunks, list):
            trimmed_context["chunks"] = [str(chunk)[:600] for chunk in chunks[:8]]
        result["retrieval_context"] = trimmed_context

    required_schema = result.get("required_schema")
    if isinstance(required_schema, dict):
        result["required_schema"] = {"type": required_schema.get("type", "object")}

    reduced_size = len(json.dumps(result, ensure_ascii=False))
    _log_event("AGENT_PAYLOAD_SIZE", size=original_size, reduced_size=reduced_size, max_size=MAX_AGENT_PAYLOAD_CHARS, truncated=True)
    return result


def _urlopen_json(request: urllib.request.Request, timeout: int, provider: str, model: str) -> dict[str, Any]:
    """Execute HTTP request with consistent diagnostics for provider failures."""

    full_url = request.full_url
    _log_event("PROVIDER_REQUEST", provider=provider, model=model, url=full_url, timeout=timeout, payload_size=len(request.data or b""))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            _log_event("PROVIDER_RESPONSE", provider=provider, model=model, status=getattr(response, "status", None), body=_summarize_text(body, 500))
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="ignore")
        _log_event("PROVIDER_HTTP_ERROR", provider=provider, model=model, status=exc.code, url=full_url, body=_summarize_text(raw_body, 500))
        raise
    except Exception as exc:
        _log_event("PROVIDER_NETWORK_ERROR", provider=provider, model=model, url=full_url, exception_type=type(exc).__name__, exception_message=str(exc))
        raise


def _resolve_gemini_model(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return DEFAULT_GEMINI_MODEL
    return GEMINI_MODEL_ALIASES.get(normalized, normalized)

def sanitize_review_findings(review: dict[str, Any]) -> dict[str, Any]:

    review = dict(review)

    ambiguities = review.get(
        "ambiguous_requirements",
        [],
    )

    filtered = []

    for finding in ambiguities:

        text = str(finding).lower()

        if any(
            keyword in text
            for keyword in NON_BLOCKING_KEYWORDS
        ):
            continue

        filtered.append(finding)

    review["ambiguous_requirements"] = filtered

    return review


def run_prd_pipeline(prd_text: str, options: PipelineOptions | None = None) -> dict[str, Any]:
    """Run the full PRD quality workflow from analysis to automation-design generation.

    WHY this exists:
    - Keeps a single orchestrator for the API route so entrypoint behavior is deterministic.
    - Applies quality gates before downstream processing to prevent garbage-in propagation.
    - Preserves auditable stage outputs for debugging and UI visibility.
    """
    options = options or PipelineOptions()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    audit_log: list[dict[str, Any]] = []
    quality_gate = evaluate_prd_text_quality(prd_text)

    # STEP 1: Analyze PRD into structured requirements.
    # Input: raw normalized PRD text + lightweight retrieval context.
    # Output: validated Agent-1 structure (`VALID_PRD` or `REJECTED`).
    context = build_retrieval_context(prd_text)
    agent_1_output = call_structured_agent(
        "prd_analyst",
        {
            "prd_extract": prd_text,
            "retrieval_context": context,
            "quality_gate": quality_gate,
        },
        options,
        quality_gate=quality_gate,
    )
    agent_1_output = apply_agent1_quality_gate(agent_1_output, quality_gate)
    audit_log.append({"agent": "prd_analyst", "decision": agent_1_output.get("decision")})

    if agent_1_output.get("status") == "REJECTED" or agent_1_output.get("decision") == "REJECT":
        return {
            "status": "REJECTED",
            "reason": "Input does not look like a valid software PRD.",
            "started_at": started,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_1": agent_1_output,
            "audit_log": audit_log,
        }

    # STEP 2: Reviewer validates requirement completeness and testability.
    # Input: original PRD + Agent-1 structure.
    # Output: APPROVED or REWORK_REQUIRED with findings.
    review_result = None
    loop_count = 0
    while loop_count < MAX_REVIEW_LOOPS:
        loop_count += 1
        review_result = call_structured_agent(
            "prd_reviewer",
            {
                "prd_extract": prd_text,
                "agent_1_output": agent_1_output,
                "review_loop": loop_count,
            },
            options,
        )
        review_result = sanitize_review_findings(
            review_result
        )
        audit_log.append(
            {
                "agent": "prd_reviewer",
                "loop": loop_count,
                "decision": review_result.get("decision"),
            }
        )

        if review_result.get("decision") in (
                "APPROVED",
                "APPROVED_WITH_OBSERVATIONS",
        ):
            break

        # STEP 2b: Rework Agent-1 output using reviewer feedback.
        # Input: previous Agent-1 output + reviewer findings.
        # Output: revised validated Agent-1 structure.
        agent_1_output = call_structured_agent(
            "prd_analyst",
            {
                "prd_extract": prd_text,
                "retrieval_context": context,
                "quality_gate": quality_gate,
                "previous_output": agent_1_output,
                "review_feedback": review_result,
            },
            options,
            quality_gate=quality_gate,
        )
        audit_log.append({"agent": "prd_analyst", "loop": loop_count, "decision": "REWORKED"})

    if review_result.get("decision") == "REWORK_REQUIRED":
        agent_1_output = call_structured_agent(
            "prd_analyst",
            {
                "prd_extract": prd_text,
                "retrieval_context": context,
                "quality_gate": quality_gate,
                "previous_output": agent_1_output,
                "review_feedback": review_result,
            },
            options,
            quality_gate=quality_gate,
        )

        audit_log.append(
            {
                "agent": "prd_analyst",
                "loop": loop_count,
                "decision": "REWORKED",
            }
        )

    # STEP 3: Generate test design from approved requirements.
    # Input: approved Agent-1 structure + reviewer decision.
    # Output: validated story/epic test designs + traceability.
    test_design = call_structured_agent(
        "test_designer",
        {
            "approved_prd_structure": agent_1_output,
            "review_result": review_result,
        },
        options,
    )
    audit_log.append({"agent": "test_designer", "decision": "COMPLETE"})

    # STEP 4: Convert test design into automation-ready artifacts.
    # Input: approved requirements + test design + chosen framework.
    # Output: validated automation suites and CI guidance.
    automation_design = call_structured_agent(
        "automation_designer",
        {
            "approved_prd_structure": agent_1_output,
            "test_design": test_design,
            "automation_framework": options.automation_framework,
        },
        options,
    )
    audit_log.append({"agent": "automation_designer", "decision": "COMPLETE"})

    return {
        "status": "APPROVED",
        "started_at": started,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "review_loops": loop_count,
        "agent_1_prd_structure": agent_1_output,
        "agent_2_review": review_result,
        "agent_3_test_design": test_design,
        "agent_4_automation_design": automation_design,
        "audit_log": audit_log,
    }


def build_retrieval_context(text: str) -> dict[str, Any]:
    """Build a lightweight retrieval context for grounding prompts.

    WHY this exists:
    This baseline RAG context ensures prompts carry the most relevant chunks even
    before a full vector search subsystem is introduced.
    """
    chunks = chunk_text(text)
    keywords = [
        "goal",
        "feature",
        "user",
        "persona",
        "acceptance",
        "criteria",
        "demo",
        "requirement",
        "integration",
        "api",
        "workflow",
        "report",
        "dashboard",
    ]
    ranked = []
    for index, chunk in enumerate(chunks):
        score = sum(1 for word in keywords if word in chunk.lower())
        if score:
            ranked.append({"chunk_id": f"PRD-{index + 1}", "score": score, "text": chunk})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {
        "retrieval_method": "local_keyword_baseline",
        "note": "Replace with embeddings/vector DB for production RAG.",
        "top_chunks": ranked[:8],
    }


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Split text into overlapping windows so prompts can cite local context reliably."""
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        chunks.append(clean[start : start + size])
        start += max(size - overlap, 1)
    return chunks


def call_structured_agent(
    agent_key: str,
    payload: dict[str, Any],
    options: PipelineOptions,
    quality_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call one LLM-backed pipeline stage and validate output.

    WHY this exists:
    The active PRD execution pipeline is intentionally LLM-first and should not
    silently degrade to template-generated artifacts in production.

    Input schema:
    - `agent_key`: one of `prd_analyst`, `prd_reviewer`, `test_designer`, `automation_designer`
    - `payload`: JSON-serializable stage payload
    - `options`: provider/model/runtime selection
    - `quality_gate`: optional gate metrics consumed by Agent 1 validation

    Output schema:
    - stage-specific validated dict produced by `_validate_agent_response`
    """

    if not options.use_llm:
        raise PipelineExecutionError("use_llm=False is no longer supported in the active production PRD pipeline")

    prepared_payload = _prepare_payload_for_llm(payload)
    try:
        if options.provider == "cloud":
            response = call_gemini_json(
                options.cloud_model,
                options.cloud_api_key,
                AGENT_PROMPTS[agent_key],
                prepared_payload,
            )
        else:
            response = call_ollama_json(
                options.ollama_url,
                options.model,
                AGENT_PROMPTS[agent_key],
                prepared_payload,
            )
    except Exception as exc:
        hint = ""
        if options.provider == "local" and isinstance(exc, TimeoutError):
            hint = " Local Ollama model did not respond in time. Verify model health in Ollama or switch local model/provider."
        elif options.provider == "local" and isinstance(exc, urllib.error.HTTPError):
            hint = " Local Ollama returned an HTTP error. Check model files/runtime health and try a different local model."
        _log_event(
            "PROVIDER_CALL_FAILED",
            agent=agent_key,
            provider=options.provider,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        raise PipelineExecutionError(
            f"Agent '{agent_key}' failed for provider '{options.provider}': {type(exc).__name__}: {exc}.{hint}"
        ) from exc

    return _validate_agent_response(agent_key, response, quality_gate=quality_gate)


def evaluate_prd_text_quality(text: str) -> dict[str, Any]:
    """Evaluate whether extracted text is meaningful enough for PRD analysis.

    WHY this exists:
    Agent outputs are only as good as extracted text quality. This gate blocks
    obvious decoding artifacts from flowing into downstream planning/test stages.
    """
    compact = re.sub(r"\s+", "", text or "")
    words = re.findall(r"\b[\w-]{2,}\b", text or "", flags=re.UNICODE)
    product_terms = {
        "feature",
        "requirements",
        "acceptance",
        "criteria",
        "user",
        "story",
        "epic",
        "scope",
        "workflow",
        "api",
        "dashboard",
        "module",
    }
    lower_words = {w.lower() for w in words}
    domain_hits = sorted(term for term in product_terms if term in lower_words)
    null_ratio = (compact.count("\x00") / len(compact)) if compact else 0.0
    ascii_ratio = (
        sum(1 for ch in compact if (ch.isascii() and ch.isprintable()) or ch in "\n\t") / len(compact)
        if compact
        else 0.0
    )
    meaningful = len(words) >= 30 and len(domain_hits) >= 2 and null_ratio < 0.1 and ascii_ratio > 0.55
    reasons: list[str] = []
    if len(words) < 30:
        reasons.append("Document contains too little natural language text for PRD analysis.")
    if len(domain_hits) < 2:
        reasons.append("Document is missing common software PRD terms (feature, requirements, acceptance criteria, etc.).")
    if null_ratio >= 0.1:
        reasons.append("Document contains a high amount of null/control characters, likely from incorrect decoding.")
    if ascii_ratio <= 0.55:
        reasons.append("Document text has too many non-printable or non-readable characters.")
    return {
        "is_meaningful": meaningful,
        "word_count": len(words),
        "domain_hits": domain_hits,
        "null_char_ratio": round(null_ratio, 4),
        "readable_ascii_ratio": round(ascii_ratio, 4),
        "reasons": reasons,
    }


def apply_agent1_quality_gate(agent_output: dict[str, Any], quality_gate: dict[str, Any]) -> dict[str, Any]:
    """Apply pre-analysis text quality gate to Agent 1 output.

    Input schema:
    - `agent_output`: Agent 1 JSON output (dict)
    - `quality_gate`: quality metrics dict from `evaluate_prd_text_quality`

    Output schema:
    - Dict with original agent fields, and when rejected:
      - adds `quality_gate`
      - merges/sets `rejection_reasons`
      - forces `decision` to `REJECT`
    """
    if quality_gate.get("is_meaningful"):
        return agent_output
    result = dict(agent_output or {})
    result["decision"] = "REJECT"
    result["status"] = "REJECTED"
    existing_reasons = result.get("rejection_reasons")
    merged = []
    if isinstance(existing_reasons, list):
        merged.extend(str(reason) for reason in existing_reasons if str(reason).strip())
    merged.extend(quality_gate.get("reasons") or [])
    result["rejection_reasons"] = merged or ["Extracted PRD text is not meaningful."]
    result["quality_gate"] = quality_gate
    return result


def call_ollama_json(ollama_url: str, model: str, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call Ollama chat endpoint and parse structured JSON response.

    WHY this exists:
    It centralizes transport logging and parse diagnostics so provider failures
    can be distinguished from JSON extraction/validation failures.
    """
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1200,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    tags_request = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
    tags_payload = _urlopen_json(tags_request, timeout=10, provider="ollama", model=model)
    available_models = [
        str(item.get("name") or "")
        for item in (tags_payload.get("models") or [])
        if isinstance(item, dict)
    ]
    if model not in available_models:
        raise ValueError(f"Ollama model '{model}' is not available. Installed models: {available_models}")

    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        data = _urlopen_json(request, timeout=OLLAMA_CHAT_TIMEOUT_SECONDS, provider="ollama", model=model)
        content = data.get("message", {}).get("content", "{}")
    except TimeoutError:
        _log_event("OLLAMA_CHAT_TIMEOUT_FALLBACK", model=model, fallback_endpoint="/api/generate")
        generate_body = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 1200,
            },
            "prompt": (
                f"System instruction:\n{system_prompt}\n\n"
                f"User request:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
        }
        generate_request = urllib.request.Request(
            f"{ollama_url.rstrip('/')}/api/generate",
            data=json.dumps(generate_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        generate_data = _urlopen_json(
            generate_request,
            timeout=OLLAMA_CHAT_TIMEOUT_SECONDS,
            provider="ollama",
            model=model,
        )
        content = str(generate_data.get("response") or "{}")
    _log_event("RAW_LLM_RESPONSE", provider="ollama", model=model, summary=_summarize_text(content))
    extracted_json = extract_json(content)
    _log_event("EXTRACTED_JSON", provider="ollama", model=model, summary=_summarize_text(extracted_json))
    parsed = json.loads(extracted_json)
    _log_event("PARSED_RESPONSE", provider="ollama", model=model, keys=sorted(parsed.keys()) if isinstance(parsed, dict) else [])
    return parsed


def call_gemini_json(model: str, api_key: str, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini API and parse structured JSON response with diagnostics."""

    if not api_key:
        raise ValueError("Cloud API key is required for PRD pipeline cloud mode")
    resolved_model = _resolve_gemini_model(model)
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"System instruction:\n{system_prompt}\n\n"
                            f"User request:\n{json.dumps(payload, ensure_ascii=False)}"
                        )
                    }
                ]
            }
        ]
    }
    endpoint_versions = [GEMINI_API_VERSION]
    if GEMINI_FALLBACK_API_VERSION and GEMINI_FALLBACK_API_VERSION not in endpoint_versions:
        endpoint_versions.append(GEMINI_FALLBACK_API_VERSION)

    data = None
    last_error: Exception | None = None
    for version in endpoint_versions:
        request = urllib.request.Request(
            f"{GEMINI_API_BASE.rstrip('/')}/{version}/models/{resolved_model}:generateContent?key={api_key}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            data = _urlopen_json(request, timeout=GEMINI_CHAT_TIMEOUT_SECONDS, provider="gemini", model=resolved_model)
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404 and version != endpoint_versions[-1]:
                continue
            raise
    if data is None and last_error is not None:
        raise last_error
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    content = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    _log_event("RAW_LLM_RESPONSE", provider="gemini", model=resolved_model, summary=_summarize_text(content))
    extracted_json = extract_json(content or "{}")
    _log_event("EXTRACTED_JSON", provider="gemini", model=resolved_model, summary=_summarize_text(extracted_json))
    parsed = json.loads(extracted_json)
    _log_event("PARSED_RESPONSE", provider="gemini", model=resolved_model, keys=sorted(parsed.keys()) if isinstance(parsed, dict) else [])
    return parsed


def extract_json(text: str) -> str:
    """Extract first JSON object substring from model output text."""
    text = text.strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)
