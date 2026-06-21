import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_REVIEW_LOOPS = 3


AGENT_PROMPTS = {
    "prd_analyst": """You are Agent 1: PRD Analyst.
Your job:
1. Decide if the input is a real software PRD or enhancement document.
2. If it is not a PRD, reject it with clear reasons.
3. If it is a PRD, identify product goal, target personas, features, assumptions, risks, epics, user stories, acceptance criteria, and demo points.
Return strict JSON only.""",
    "prd_reviewer": """You are Agent 2: PRD Reviewer.
Review Agent 1's output for correctness.
Check:
- Are epics logically derived from the PRD?
- Are user stories clear and testable?
- Are acceptance criteria written in a measurable way?
- Are demo points actually demoable?
- Are personas and product goals clear?
Return strict JSON only with decision APPROVE or REWORK.""",
    "test_designer": """You are Agent 3: Test Designer.
Create test coverage from approved epics and user stories.
Return strict JSON only with:
- component_test_cases for each user story
- epic_e2e_tests for each epic
- must_have_unit_tests
- pact_contract_tests
- traceability_matrix""",
    "automation_designer": """You are Agent 4: Automation Designer.
Generate automation-ready test cases using the selected framework: Playwright or Selenium.
Include:
- test suites
- selectors or locator strategy
- test data
- setup and teardown
- Alumnium opportunities using high-level do/check/get instructions
- CI execution notes
Return strict JSON only.""",
}


@dataclass
class PipelineOptions:
    automation_framework: str = "playwright"
    model: str = DEFAULT_MODEL
    ollama_url: str = DEFAULT_OLLAMA_URL
    use_llm: bool = True


def run_prd_pipeline(prd_text: str, options: PipelineOptions | None = None) -> dict[str, Any]:
    options = options or PipelineOptions()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    audit_log: list[dict[str, Any]] = []

    context = build_retrieval_context(prd_text)
    agent_1_output = call_structured_agent(
        "prd_analyst",
        {
            "prd_extract": prd_text,
            "retrieval_context": context,
            "required_schema": prd_analyst_schema(),
        },
        options,
        fallback=lambda: heuristic_prd_analysis(prd_text, context),
    )
    audit_log.append({"agent": "prd_analyst", "decision": agent_1_output.get("decision")})

    if agent_1_output.get("decision") == "REJECT":
        return {
            "status": "REJECTED",
            "reason": "Input does not look like a valid software PRD.",
            "started_at": started,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_1": agent_1_output,
            "audit_log": audit_log,
        }

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
                "required_schema": reviewer_schema(),
            },
            options,
            fallback=lambda: heuristic_review(agent_1_output),
        )
        audit_log.append(
            {
                "agent": "prd_reviewer",
                "loop": loop_count,
                "decision": review_result.get("decision"),
            }
        )

        if review_result.get("decision") == "APPROVE":
            break

        agent_1_output = call_structured_agent(
            "prd_analyst",
            {
                "prd_extract": prd_text,
                "retrieval_context": context,
                "previous_output": agent_1_output,
                "review_feedback": review_result,
                "required_schema": prd_analyst_schema(),
            },
            options,
            fallback=lambda: rework_prd_analysis(agent_1_output, review_result),
        )
        audit_log.append({"agent": "prd_analyst", "loop": loop_count, "decision": "REWORKED"})

    if not review_result or review_result.get("decision") != "APPROVE":
        return {
            "status": "NEEDS_CLARITY",
            "reason": "Reviewer requested rework more than 3 times. Ask user to rewrite the PRD or add clarity.",
            "started_at": started,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_1": agent_1_output,
            "agent_2": review_result,
            "audit_log": audit_log,
        }

    test_design = call_structured_agent(
        "test_designer",
        {
            "approved_prd_structure": agent_1_output,
            "review_result": review_result,
            "required_schema": test_designer_schema(),
        },
        options,
        fallback=lambda: heuristic_test_design(agent_1_output),
    )
    audit_log.append({"agent": "test_designer", "decision": "COMPLETE"})

    automation_design = call_structured_agent(
        "automation_designer",
        {
            "approved_prd_structure": agent_1_output,
            "test_design": test_design,
            "automation_framework": options.automation_framework,
            "required_schema": automation_schema(),
        },
        options,
        fallback=lambda: heuristic_automation_design(agent_1_output, test_design, options.automation_framework),
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
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        chunks.append(clean[start : start + size])
        start += max(size - overlap, 1)
    return chunks


def call_structured_agent(agent_key: str, payload: dict[str, Any], options: PipelineOptions, fallback):
    if not options.use_llm:
        return fallback()
    try:
        response = call_ollama_json(
            options.ollama_url,
            options.model,
            AGENT_PROMPTS[agent_key],
            payload,
        )
        if isinstance(response, dict):
            return response
    except Exception:
        pass
    return fallback()


def call_ollama_json(ollama_url: str, model: str, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data.get("message", {}).get("content", "{}")
    return json.loads(extract_json(content))


def extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return match.group(0)


def heuristic_prd_analysis(text: str, context: dict[str, Any]) -> dict[str, Any]:
    lower = text.lower()
    signals = ["feature", "user", "requirement", "acceptance", "persona", "workflow", "api", "dashboard"]
    if sum(1 for signal in signals if signal in lower) < 2:
        return {
            "decision": "REJECT",
            "rejection_reasons": [
                "The document does not clearly describe a software feature or enhancement.",
                "Missing product goal, target users, and testable acceptance criteria.",
            ],
            "missing_information": ["feature scope", "target persona", "expected behavior", "success criteria"],
        }

    personas = infer_personas(text)
    epics = build_default_epics(text)
    return {
        "decision": "ACCEPT",
        "prd_summary": summarize_text(text),
        "target_personas": personas,
        "product_goal": "Deliver the requested software capability with measurable user value and clear acceptance criteria.",
        "epics": epics,
        "demo_highlights": [
            "Show the main happy-path workflow end to end.",
            "Show validation or error handling for important edge cases.",
            "Show reporting, audit, notification, or integration behavior if present in the PRD.",
        ],
        "assumptions": [
            "Authentication and base application navigation already exist.",
            "Detailed UI designs and API contracts will be confirmed before development.",
        ],
        "risks": [
            "PRD may not contain enough non-functional requirements.",
            "Integration behavior may need explicit API contract confirmation.",
        ],
        "rag_citations": [chunk["chunk_id"] for chunk in context.get("top_chunks", [])[:5]],
    }


def infer_personas(text: str) -> list[dict[str, str]]:
    lower = text.lower()
    personas = []
    if "admin" in lower:
        personas.append({"name": "Admin User", "goal": "Configure and monitor the feature."})
    if "customer" in lower or "end user" in lower:
        personas.append({"name": "End User", "goal": "Complete the main workflow with minimal friction."})
    if "manager" in lower or "report" in lower:
        personas.append({"name": "Manager", "goal": "Track outcomes and review status."})
    return personas or [{"name": "Primary User", "goal": "Use the feature to complete the described business task."}]


def build_default_epics(text: str) -> list[dict[str, Any]]:
    theme = summarize_text(text, 110)
    return [
        {
            "id": "EPIC-1",
            "title": "Core User Workflow",
            "description": f"Implement the main workflow described in the PRD: {theme}",
            "target_persona": "Primary User",
            "demo_points": ["User can complete the main workflow from start to finish."],
            "user_stories": [
                {
                    "id": "US-1.1",
                    "title": "Complete primary action",
                    "story": "As a primary user, I want to complete the main feature workflow so that I can achieve the business goal.",
                    "acceptance_criteria": [
                        "Given valid input, when the user submits the workflow, then the system saves the result successfully.",
                        "Given missing required input, when the user submits the workflow, then the system shows clear validation messages.",
                        "Given the action is completed, when the user views the result, then the latest status is visible.",
                    ],
                }
            ],
        },
        {
            "id": "EPIC-2",
            "title": "Admin, Audit, And Error Handling",
            "description": "Add operational controls, error handling, and traceable outcomes for the feature.",
            "target_persona": "Admin User",
            "demo_points": ["Admin can review status, failures, and important audit details."],
            "user_stories": [
                {
                    "id": "US-2.1",
                    "title": "Handle exceptions safely",
                    "story": "As an admin user, I want failures to be visible and recoverable so that support can resolve issues quickly.",
                    "acceptance_criteria": [
                        "Given a downstream failure, when the workflow runs, then the system records a clear failure status.",
                        "Given a failed transaction, when an admin reviews it, then error details and retry guidance are visible.",
                    ],
                }
            ],
        },
    ]


def heuristic_review(agent_1_output: dict[str, Any]) -> dict[str, Any]:
    epics = agent_1_output.get("epics") or []
    findings = []
    if not epics:
        findings.append("No epics found.")
    for epic in epics:
        if not epic.get("user_stories"):
            findings.append(f"{epic.get('id', 'Epic')} has no user stories.")
        for story in epic.get("user_stories", []):
            if len(story.get("acceptance_criteria", [])) < 2:
                findings.append(f"{story.get('id', 'Story')} needs more acceptance criteria.")
    return {
        "decision": "APPROVE" if not findings else "REWORK",
        "findings": findings,
        "quality_score": 88 if not findings else 55,
        "rework_instructions": findings,
    }


def rework_prd_analysis(agent_1_output: dict[str, Any], review_result: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(agent_1_output))
    updated.setdefault("assumptions", []).append("Reworked after reviewer feedback.")
    updated["review_feedback_addressed"] = review_result.get("rework_instructions", [])
    return updated


def heuristic_test_design(agent_1_output: dict[str, Any]) -> dict[str, Any]:
    component_tests = []
    e2e_tests = []
    unit_tests = []
    pact_tests = []
    traceability = []
    for epic in agent_1_output.get("epics", []):
        e2e_tests.append(
            {
                "epic_id": epic["id"],
                "title": f"E2E: {epic['title']}",
                "steps": ["Login as target persona", "Navigate to feature", "Complete workflow", "Verify final status"],
                "expected_result": "The epic workflow is completed and visible to the user.",
            }
        )
        for story in epic.get("user_stories", []):
            component_tests.append(
                {
                    "story_id": story["id"],
                    "title": f"Component tests for {story['title']}",
                    "positive_tests": story.get("acceptance_criteria", [])[:2],
                    "negative_tests": ["Invalid input is rejected with a helpful message."],
                    "edge_tests": ["Boundary values and duplicate submissions are handled safely."],
                }
            )
            unit_tests.append(
                {
                    "story_id": story["id"],
                    "must_have": ["validation rules", "state transitions", "error mapping", "permission checks"],
                }
            )
            pact_tests.append(
                {
                    "story_id": story["id"],
                    "consumer": "frontend or calling service",
                    "provider": "feature API or downstream service",
                    "contract": "Request/response shape and error status must be contract-tested.",
                }
            )
            traceability.append({"epic_id": epic["id"], "story_id": story["id"], "coverage": "component + e2e + unit + pact"})
    return {
        "component_test_cases": component_tests,
        "epic_e2e_tests": e2e_tests,
        "must_have_unit_tests": unit_tests,
        "pact_contract_tests": pact_tests,
        "traceability_matrix": traceability,
    }


def heuristic_automation_design(
    agent_1_output: dict[str, Any], test_design: dict[str, Any], framework: str
) -> dict[str, Any]:
    framework = framework.lower()
    suites = []
    for e2e in test_design.get("epic_e2e_tests", []):
        suites.append(
            {
                "name": e2e["title"],
                "framework": framework,
                "test_type": "e2e",
                "steps": e2e["steps"],
                "locator_strategy": "Prefer role, label, test id, and stable accessible names.",
                "alumnium_optional_steps": [
                    "al.do('complete the main workflow using valid data')",
                    "al.check('success status is visible to the user')",
                    "al.get('final workflow reference number')",
                ],
            }
        )
    return {
        "selected_framework": framework,
        "recommended_stack": {
            "playwright": ["pytest-playwright or @playwright/test", "Alumnium optional AI-assisted layer"],
            "selenium": ["Selenium WebDriver", "Alumnium optional AI-assisted layer"],
        }.get(framework, ["Playwright is recommended by default"]),
        "automation_suites": suites,
        "ci_notes": [
            "Run smoke tests on every pull request.",
            "Run full regression nightly.",
            "Store screenshots, traces, and logs for failed tests.",
        ],
        "alumnium_guidance": "Use Alumnium for resilient high-level actions/verifications, while keeping critical flows backed by deterministic selectors and assertions.",
    }


def summarize_text(text: str, max_chars: int = 240) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:max_chars].rstrip() + ("..." if len(clean) > max_chars else "")


def prd_analyst_schema() -> dict[str, Any]:
    return {"decision": "ACCEPT|REJECT", "prd_summary": "string", "target_personas": [], "epics": []}


def reviewer_schema() -> dict[str, Any]:
    return {"decision": "APPROVE|REWORK", "quality_score": "number", "findings": [], "rework_instructions": []}


def test_designer_schema() -> dict[str, Any]:
    return {"component_test_cases": [], "epic_e2e_tests": [], "must_have_unit_tests": [], "pact_contract_tests": []}


def automation_schema() -> dict[str, Any]:
    return {"selected_framework": "playwright|selenium", "automation_suites": [], "alumnium_guidance": "string"}
