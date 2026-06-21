from __future__ import annotations

from typing import Any

from agents.llm import call_structured_json


class QEStrategyAgent:
    name = "Agent 3 - QE Strategy Agent"

    SYSTEM_PROMPT = """You are a QE strategy expert.
Given approved PRD requirements (epics and stories), return strict JSON with keys:
- strategy: array of objects with requirement and test recommendations by test type
- coverage_matrix: array of objects with requirement, test_type, priority, risk
Cover unit, API, component, integration, contract, e2e, performance, and security testing.
Be specific to the requirement text and priority."""

    def run(self, approved_requirements: dict[str, Any]) -> dict[str, Any]:
        try:
            llm_output = call_structured_json(
                self.SYSTEM_PROMPT,
                {"approved_requirements": approved_requirements},
            )
            strategy = llm_output.get("strategy") if isinstance(llm_output.get("strategy"), list) else []
            coverage = llm_output.get("coverage_matrix") if isinstance(llm_output.get("coverage_matrix"), list) else []
            if strategy and coverage:
                return {
                    "agent": self.name,
                    "strategy": strategy,
                    "coverage_matrix": coverage,
                }
        except Exception:
            pass

        recommendations = []
        coverage = []
        for epic in approved_requirements["epics"]:
            for story in epic["user_stories"]:
                requirement = f"{epic['id']} / {story['id']} - {story['title']}"
                priority = story.get("priority", "Medium")
                risk = "High" if priority == "High" else "Medium"
                recommendations.append(
                    {
                        "requirement": requirement,
                        "unit_tests": [
                            "Validate business rule functions.",
                            "Validate required field checks.",
                            "Validate error mapping and state transitions.",
                        ],
                        "api_tests": [
                            "Verify successful request and response schema.",
                            "Verify validation errors and authorization failures.",
                        ],
                        "component_tests": [
                            "Verify form rendering and user interactions.",
                            "Verify client-side validation and state updates.",
                        ],
                        "integration_tests": [
                            "Verify data persists through UI to API to storage.",
                            "Verify downstream service failure behavior.",
                        ],
                        "contract_tests": [
                            "Add PACT between frontend consumer and backend provider for request/response schema.",
                            "Add PACT for error responses used by the UI.",
                        ],
                        "e2e_tests": [
                            "Validate the main happy-path journey.",
                            "Validate a critical negative journey.",
                        ],
                        "performance_tests": [
                            "Check response time for main API under expected load.",
                            "Check dashboard/page load time with realistic data volume.",
                        ],
                        "security_tests": [
                            "Verify unauthorized users cannot access the workflow.",
                            "Verify input sanitization and role-based access.",
                        ],
                    }
                )
                for test_type in ("Unit", "API", "Component", "Integration", "Contract", "E2E", "Performance", "Security"):
                    coverage.append(
                        {
                            "requirement": requirement,
                            "test_type": test_type,
                            "priority": priority if test_type in ("E2E", "API", "Contract") else "Medium",
                            "risk": risk if test_type in ("E2E", "Security", "Contract") else "Medium",
                        }
                    )
        return {
            "agent": self.name,
            "strategy": recommendations,
            "coverage_matrix": coverage,
        }
