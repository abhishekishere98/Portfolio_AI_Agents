from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.agent1_prd_analyzer import PRDAnalyzer
from agents.agent2_requirement_reviewer import RequirementReviewer
from agents.agent3_qe_strategy import QEStrategyAgent
from agents.agent4_test_design import TestDesignAgent
from agents.agent5_automation_generator import AutomationGenerator
from agents.common import load_knowledge, read_text_file, write_json


MAX_REVIEW_CYCLES = 3


class PRDQualityWorkflow:
    def __init__(self, confidence_threshold: int = 65) -> None:
        self.knowledge = load_knowledge()
        self.agent1 = PRDAnalyzer(confidence_threshold=confidence_threshold)
        self.agent2 = RequirementReviewer()
        self.agent3 = QEStrategyAgent()
        self.agent4 = TestDesignAgent()
        self.agent5 = AutomationGenerator()

    def run(self, prd_text: str, automation_framework: str = "playwright") -> dict[str, Any]:
        audit_log: list[dict[str, Any]] = []
        feedback: list[str] = []
        analyzer_output: dict[str, Any] = {}
        reviewer_output: dict[str, Any] = {}

        for cycle in range(1, MAX_REVIEW_CYCLES + 1):
            analyzer_output = self.agent1.run(prd_text, feedback=feedback)
            audit_log.append({"agent": "Agent 1 - PRD Analyzer", "cycle": cycle, "status": analyzer_output["status"]})
            if analyzer_output["status"] != "VALID_PRD":
                return {
                    "status": "REJECTED",
                    "message": "Document is not a valid software PRD",
                    "agent_1": analyzer_output,
                    "audit_log": audit_log,
                }

            reviewer_output = self.agent2.run(analyzer_output)
            audit_log.append({"agent": "Agent 2 - Requirement Reviewer", "cycle": cycle, "decision": reviewer_output["decision"]})
            if reviewer_output["decision"] == "APPROVED":
                break
            feedback = reviewer_output["feedback"]
        else:
            return {
                "status": "NEEDS_HUMAN_CLARIFICATION",
                "message": "Maximum 3 review cycles reached. Please clarify or rewrite the PRD.",
                "agent_1": analyzer_output,
                "agent_2": reviewer_output,
                "audit_log": audit_log,
            }

        strategy_output = self.agent3.run(analyzer_output)
        audit_log.append({"agent": "Agent 3 - QE Strategy Agent", "status": "COMPLETE"})
        test_design_output = self.agent4.run(analyzer_output)
        audit_log.append({"agent": "Agent 4 - Test Design Agent", "status": "COMPLETE"})
        automation_output = self.agent5.run(analyzer_output, test_design_output, automation_framework)
        audit_log.append({"agent": "Agent 5 - Automation Generator", "status": "COMPLETE"})

        return {
            "status": "APPROVED",
            "knowledge_used": sorted(self.knowledge.keys()),
            "agent_1_prd_analysis": analyzer_output,
            "agent_2_requirement_review": reviewer_output,
            "agent_3_qe_strategy": strategy_output,
            "agent_4_test_design": test_design_output,
            "agent_5_automation": automation_output,
            "audit_log": audit_log,
        }


def run_from_file(input_path: str | Path, output_dir: str | Path, automation_framework: str = "playwright") -> dict[str, Any]:
    prd_text = read_text_file(input_path)
    result = PRDQualityWorkflow().run(prd_text, automation_framework=automation_framework)
    write_outputs(result, output_dir)
    return result


def write_outputs(result: dict[str, Any], output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "workflow_result.json", result)

    if result["status"] != "APPROVED":
        (output / "rejection.md").write_text(result["message"], encoding="utf-8")
        return

    (output / "epics_user_stories.md").write_text(render_epics(result["agent_1_prd_analysis"]), encoding="utf-8")
    (output / "test_strategy.json").write_text(
        json.dumps(result["agent_3_qe_strategy"], indent=2),
        encoding="utf-8",
    )
    (output / "test_cases_story_level.md").write_text(
        result["agent_4_test_design"]["story_level_markdown"],
        encoding="utf-8",
    )
    (output / "test_cases_epic_level.md").write_text(
        result["agent_4_test_design"]["epic_level_markdown"],
        encoding="utf-8",
    )

    for relative_path, content in result["agent_5_automation"]["files"].items():
        target = output / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def render_epics(analysis: dict[str, Any]) -> str:
    lines = [
        f"# {analysis['product_name']} - Epics And User Stories",
        "",
        f"Business Goal: {analysis['business_goal']}",
        "",
        f"Confidence Score: {analysis['confidence_score']}",
        "",
        "## Personas",
    ]
    for persona in analysis["personas"]:
        lines.append(f"- {persona['name']}: {persona['goal']}")
    lines.extend(["", "## Epics"])
    for epic in analysis["epics"]:
        lines.extend(
            [
                "",
                f"### {epic['id']} - {epic['title']}",
                "",
                epic["description"],
                "",
                f"Target Persona: {epic['target_persona']}",
                "",
                "Demo Scenarios:",
            ]
        )
        lines.extend(f"- {item}" for item in epic["demo_scenarios"])
        lines.append("")
        for story in epic["user_stories"]:
            lines.extend(
                [
                    f"#### {story['id']} - {story['title']}",
                    "",
                    story["story"],
                    "",
                    f"Priority: {story['priority']}",
                    "",
                    "Acceptance Criteria:",
                ]
            )
            lines.extend(f"- {item}" for item in story["acceptance_criteria"])
            lines.append("")
    return "\n".join(lines)
