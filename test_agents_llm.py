from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.agent2_requirement_reviewer import RequirementReviewer
from agents.agent3_qe_strategy import QEStrategyAgent
from agents.agent4_test_design import TestDesignAgent
from agents.agent5_automation_generator import AutomationGenerator


APPROVED_REQUIREMENTS = {
    "status": "VALID_PRD",
    "product_name": "Demo Product",
    "epics": [
        {
            "id": "E1",
            "title": "Orders",
            "target_persona": "Ops User",
            "user_stories": [
                {
                    "id": "US1",
                    "title": "Create order",
                    "priority": "High",
                    "story": "As a user, I can create an order",
                    "acceptance_criteria": [
                        "Given valid data when submit then order is created",
                        "Given invalid data when submit then validation appears",
                        "Given duplicate order when submit then warning appears",
                    ],
                }
            ],
        }
    ],
}


class AgentsLLMTests(unittest.TestCase):
    @patch("agents.agent2_requirement_reviewer.call_structured_json")
    def test_reviewer_uses_llm_output(self, mocked_call):
        mocked_call.return_value = {
            "decision": "APPROVED",
            "quality_score": 92,
            "feedback": ["Looks testable."],
            "checks": {
                "epic_quality": "PASS",
                "story_quality": "PASS",
                "acceptance_criteria": "PASS",
                "testability": "PASS",
                "demoability": "PASS",
            },
        }
        result = RequirementReviewer().run(APPROVED_REQUIREMENTS)
        self.assertEqual("APPROVED", result["decision"])
        self.assertEqual(92, result["quality_score"])

    @patch("agents.agent3_qe_strategy.call_structured_json")
    def test_qe_strategy_uses_llm_output(self, mocked_call):
        mocked_call.return_value = {
            "strategy": [{"requirement": "E1 / US1", "unit_tests": ["x"]}],
            "coverage_matrix": [{"requirement": "E1 / US1", "test_type": "Unit", "priority": "High", "risk": "High"}],
        }
        result = QEStrategyAgent().run(APPROVED_REQUIREMENTS)
        self.assertEqual(1, len(result["strategy"]))
        self.assertEqual(1, len(result["coverage_matrix"]))

    @patch("agents.agent4_test_design.call_structured_json")
    def test_test_design_uses_llm_output(self, mocked_call):
        mocked_call.return_value = {
            "story_level_tests": [
                {
                    "level": "User Story",
                    "story_id": "US1",
                    "test_type": "Functional",
                    "priority": "High",
                    "preconditions": "Ready",
                    "steps": "Do action",
                    "expected_result": "Success",
                }
            ],
            "epic_level_tests": [
                {
                    "level": "Epic E2E",
                    "epic_id": "E1",
                    "title": "E2E",
                    "priority": "High",
                    "preconditions": "Ready",
                    "steps": "Flow",
                    "expected_result": "Success",
                }
            ],
        }
        result = TestDesignAgent().run(APPROVED_REQUIREMENTS)
        self.assertIn("|", result["story_level_markdown"])
        self.assertEqual(1, len(result["story_level_tests"]))

    @patch("agents.agent5_automation_generator.call_structured_json")
    def test_automation_generator_uses_llm_files(self, mocked_call):
        mocked_call.return_value = {
            "automation_scope": "Critical paths",
            "selected_tests": [{"epic_id": "E1", "priority": "High"}],
            "files": {"automation/playwright/test_demo.py": "def test_demo():\n    assert True\n"},
        }
        result = AutomationGenerator().run(
            APPROVED_REQUIREMENTS,
            {"epic_level_tests": [{"epic_id": "E1", "priority": "High", "title": "E2E"}]},
            "playwright",
        )
        self.assertIn("automation/playwright/test_demo.py", result["files"])


if __name__ == "__main__":
    unittest.main()
