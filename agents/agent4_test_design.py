from __future__ import annotations

from typing import Any

from agents.llm import call_structured_json


class TestDesignAgent:
    name = "Agent 4 - Test Design Agent"

    SYSTEM_PROMPT = """You are a senior QA test designer.
Given approved requirements, return strict JSON with keys:
- story_level_tests: array of user-story test cases (functional/negative/boundary/error-focused)
- epic_level_tests: array of epic-level E2E tests
Use fields compatible with the current pipeline and keep tests specific and actionable."""

    def run(self, approved_requirements: dict[str, Any]) -> dict[str, Any]:
        try:
            llm_output = call_structured_json(
                self.SYSTEM_PROMPT,
                {"approved_requirements": approved_requirements},
            )
            story_tests = llm_output.get("story_level_tests") if isinstance(llm_output.get("story_level_tests"), list) else []
            epic_tests = llm_output.get("epic_level_tests") if isinstance(llm_output.get("epic_level_tests"), list) else []
            if story_tests or epic_tests:
                return {
                    "agent": self.name,
                    "story_level_tests": story_tests,
                    "epic_level_tests": epic_tests,
                    "story_level_markdown": self._markdown(story_tests),
                    "epic_level_markdown": self._markdown(epic_tests),
                }
        except Exception:
            pass

        story_tests = []
        epic_tests = []
        for epic in approved_requirements["epics"]:
            for story in epic["user_stories"]:
                story_tests.extend(
                    [
                        self._case(story, "Functional", "Valid user completes the story workflow.", "Action completes and status is visible."),
                        self._case(story, "Negative", "User submits missing or invalid required data.", "Clear validation message is shown."),
                        self._case(story, "Boundary", "User submits minimum and maximum allowed data.", "System accepts valid boundaries and rejects invalid ones."),
                        self._case(story, "Error Handling", "Downstream service returns an error.", "User sees recoverable error and system logs failure."),
                    ]
                )
            epic_tests.append(
                {
                    "level": "Epic E2E",
                    "epic_id": epic["id"],
                    "title": f"E2E validation for {epic['title']}",
                    "priority": "High",
                    "preconditions": f"User with {epic['target_persona']} access exists.",
                    "steps": "Login -> Navigate to feature -> Complete core workflow -> Verify result -> Review audit/status.",
                    "expected_result": "Business journey completes successfully and key status is visible.",
                }
            )
        return {
            "agent": self.name,
            "story_level_tests": story_tests,
            "epic_level_tests": epic_tests,
            "story_level_markdown": self._markdown(story_tests),
            "epic_level_markdown": self._markdown(epic_tests),
        }

    def _case(self, story: dict[str, Any], test_type: str, scenario: str, expected: str) -> dict[str, str]:
        return {
            "level": "User Story",
            "story_id": story["id"],
            "title": story["title"],
            "test_type": test_type,
            "priority": story.get("priority", "Medium"),
            "preconditions": "User is authenticated and has required permissions.",
            "steps": scenario,
            "expected_result": expected,
        }

    def _markdown(self, rows: list[dict[str, str]]) -> str:
        headers = ["Level", "Requirement", "Type", "Priority", "Preconditions", "Steps", "Expected Result"]
        lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        for row in rows:
            requirement = row.get("story_id") or row.get("epic_id", "")
            values = [
                row.get("level", ""),
                requirement,
                row.get("test_type", row.get("title", "")),
                row.get("priority", ""),
                row.get("preconditions", ""),
                row.get("steps", ""),
                row.get("expected_result", ""),
            ]
            lines.append("| " + " | ".join(value.replace("|", "/") for value in values) + " |")
        return "\n".join(lines)
