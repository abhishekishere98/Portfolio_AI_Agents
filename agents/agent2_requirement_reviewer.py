from __future__ import annotations

from typing import Any

from agents.llm import call_structured_json


class RequirementReviewer:
    name = "Agent 2 - Requirement Reviewer"

    SYSTEM_PROMPT = """You are a senior QA requirement reviewer.
Review PRD analysis output and return strict JSON with keys:
- decision: APPROVED or REWORK_REQUIRED
- quality_score: integer 0..100
- feedback: array of concise issues/improvements
- checks: object with keys epic_quality, story_quality, acceptance_criteria, testability, demoability (PASS|FAIL)
Base findings on testability, clarity, measurable acceptance criteria, and demo readiness."""

    def run(self, analyzer_output: dict[str, Any]) -> dict[str, Any]:
        try:
            llm_output = call_structured_json(
                self.SYSTEM_PROMPT,
                {"analyzer_output": analyzer_output},
            )
            checks = llm_output.get("checks") if isinstance(llm_output.get("checks"), dict) else {}
            return {
                "agent": self.name,
                "decision": llm_output.get("decision", "REWORK_REQUIRED"),
                "quality_score": int(llm_output.get("quality_score", 0)),
                "feedback": llm_output.get("feedback") if isinstance(llm_output.get("feedback"), list) else [],
                "checks": {
                    "epic_quality": checks.get("epic_quality", "FAIL"),
                    "story_quality": checks.get("story_quality", "FAIL"),
                    "acceptance_criteria": checks.get("acceptance_criteria", "FAIL"),
                    "testability": checks.get("testability", "FAIL"),
                    "demoability": checks.get("demoability", "FAIL"),
                },
            }
        except Exception:
            pass

        findings: list[str] = []
        if analyzer_output.get("status") != "VALID_PRD":
            return {
                "agent": self.name,
                "decision": "REWORK_REQUIRED",
                "quality_score": 0,
                "feedback": ["Agent 1 did not produce a valid PRD structure."],
            }

        epics = analyzer_output.get("epics", [])
        if not epics:
            findings.append("No epics generated.")
        for epic in epics:
            if len(epic.get("title", "")) < 5:
                findings.append(f"{epic.get('id')} epic title is too weak.")
            if not epic.get("demo_scenarios"):
                findings.append(f"{epic.get('id')} has no demo scenarios.")
            for story in epic.get("user_stories", []):
                if "As a" not in story.get("story", ""):
                    findings.append(f"{story.get('id')} is not written as a user story.")
                criteria = story.get("acceptance_criteria", [])
                if len(criteria) < 3:
                    findings.append(f"{story.get('id')} needs at least 3 acceptance criteria.")
                if not all(any(word in ac for word in ("Given", "when", "then", "Then")) for ac in criteria):
                    findings.append(f"{story.get('id')} acceptance criteria should be measurable in Given/When/Then style.")

        score = max(40, 100 - len(findings) * 12)
        return {
            "agent": self.name,
            "decision": "APPROVED" if not findings else "REWORK_REQUIRED",
            "quality_score": score,
            "feedback": findings,
            "checks": {
                "epic_quality": "PASS" if not any("epic" in item.lower() for item in findings) else "FAIL",
                "story_quality": "PASS" if not any("story" in item.lower() for item in findings) else "FAIL",
                "acceptance_criteria": "PASS" if not any("acceptance" in item.lower() for item in findings) else "FAIL",
                "testability": "PASS" if score >= 70 else "FAIL",
                "demoability": "PASS" if not any("demo" in item.lower() for item in findings) else "FAIL",
            },
        }
