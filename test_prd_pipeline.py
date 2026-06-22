from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

import prd_pipeline
from prd_pipeline import PipelineOptions, run_prd_pipeline


class PrdPipelineGateTests(unittest.TestCase):
    def test_quality_gate_rejects_garbled_text_before_downstream_agents(self):
        calls: list[str] = []

        def fake_call(agent_key, payload, options, **kwargs):
            calls.append(agent_key)
            if agent_key == "prd_analyst":
                return {
                    "status": "VALID_PRD",
                    "product_name": "Wishlist",
                    "business_goal": "Increase saved-product conversion",
                    "personas": [{"name": "Customer", "goal": "Save and revisit items"}],
                    "epics": [
                        {
                            "id": "EPIC-1",
                            "title": "Wishlist Management",
                            "description": "Manage wishlist lifecycle",
                            "source_requirement": "Users can add/remove/view wishlist items",
                            "target_persona": "Customer",
                            "user_stories": [
                                {
                                    "id": "US-1.1",
                                    "title": "Add item to wishlist",
                                    "story": "As a customer, I want to add products to wishlist so I can buy later",
                                    "priority": "High",
                                    "acceptance_criteria": ["Given product page when add clicked then item appears in wishlist"],
                                }
                            ],
                        }
                    ],
                    "assumptions": [],
                    "risks": [],
                }
            raise AssertionError(f"Downstream agent should not run when quality gate rejects: {agent_key}")

        with mock.patch.object(prd_pipeline, "call_structured_agent", side_effect=fake_call):
            result = run_prd_pipeline("\x003 \x00U \x00R \x00G", PipelineOptions(use_llm=True))

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(calls, ["prd_analyst"])
        self.assertEqual(result["agent_1"]["status"], "REJECTED")
        self.assertIn("quality_gate", result["agent_1"])
        self.assertFalse(result["agent_1"]["quality_gate"]["is_meaningful"])

    def test_meaningful_prd_can_progress_to_approved(self):
        text = (
            "Feature requirements for checkout dashboard. "
            "The user and admin workflow includes acceptance criteria, API updates, and scope details. "
            "Each user story defines expected behavior and validation cases for release quality."
        )
        responses = {
            "prd_analyst": {
                "status": "VALID_PRD",
                "product_name": "Checkout Dashboard",
                "business_goal": "Reduce checkout failures",
                "personas": [{"name": "Admin", "goal": "Monitor issues"}],
                "epics": [
                    {
                        "id": "EPIC-1",
                        "title": "Checkout Monitoring",
                        "description": "Track checkout failures and success",
                        "source_requirement": "Dashboard shows checkout success/failure trends",
                        "target_persona": "Admin",
                        "user_stories": [
                            {
                                "id": "US-1.1",
                                "title": "View checkout status trends",
                                "story": "As an admin I want trend visibility so that I can act on incidents",
                                "priority": "High",
                                "acceptance_criteria": [
                                    "Given admin dashboard when opened then success/failure trends are displayed"
                                ],
                            }
                        ],
                    }
                ],
                "assumptions": [],
                "risks": [],
            },
            "prd_reviewer": {
                "decision": "APPROVED",
                "missing_requirements": [],
                "ambiguous_requirements": [],
                "missing_acceptance_criteria": [],
                "testability_concerns": [],
            },
            "test_designer": {
                "story_level_tests": [
                    {
                        "story_id": "US-1.1",
                        "title": "Verify checkout trend chart",
                        "test_type": "Positive",
                        "priority": "High",
                        "preconditions": "Admin is authenticated",
                        "steps": "Open dashboard and inspect trend widget",
                        "expected_result": "Trend widget shows success and failure counts",
                    }
                ],
                "epic_level_tests": [
                    {
                        "epic_id": "EPIC-1",
                        "title": "Checkout monitoring E2E",
                        "priority": "High",
                        "preconditions": "Data exists",
                        "steps": "Login -> open dashboard -> validate trends",
                        "expected_result": "Monitoring flow works end-to-end",
                    }
                ],
                "traceability_matrix": [{"epic_id": "EPIC-1", "story_id": "US-1.1", "coverage": "story+epic"}],
            },
            "automation_designer": {
                "selected_framework": "playwright",
                "automation_suites": [
                    {
                        "name": "Checkout monitoring suite",
                        "framework": "playwright",
                        "test_type": "e2e",
                        "steps": ["Login as admin", "Open dashboard", "Validate trend widget"],
                        "locator_strategy": "role + test id",
                        "alumnium_optional_steps": ["al.do('open dashboard')"],
                    }
                ],
                "ci_notes": ["Run suite in PR pipeline"],
                "alumnium_guidance": "Use deterministic selectors for critical assertions",
            },
        }

        with mock.patch.object(prd_pipeline, "call_structured_agent", side_effect=lambda agent_key, payload, options, **kwargs: responses[agent_key]):
            result = run_prd_pipeline(text, PipelineOptions(use_llm=True))

        self.assertEqual(result["status"], "APPROVED")
        self.assertIn("agent_4_automation_design", result)

    def test_llm_provider_failure_does_not_silently_fallback(self):
        text = (
            "Feature requirements for checkout dashboard. "
            "The user and admin workflow includes acceptance criteria, API updates, and scope details. "
            "Each user story defines expected behavior and validation cases for release quality."
        )
        with mock.patch.object(prd_pipeline, "call_ollama_json", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(prd_pipeline.PipelineExecutionError, "timed out"):
                run_prd_pipeline(text, PipelineOptions(use_llm=True, provider="local"))

    def test_prepare_payload_for_llm_truncates_oversized_input(self):
        oversized = {
            "prd_extract": "A" * 60000,
            "retrieval_context": {
                "chunks": ["B" * 3000 for _ in range(20)],
                "top_chunks": ["C" * 2500 for _ in range(20)],
            },
            "required_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
        }

        prepared = prd_pipeline._prepare_payload_for_llm(oversized)
        self.assertLessEqual(len(prepared["prd_extract"]), int(prd_pipeline.MAX_AGENT_PAYLOAD_CHARS * 0.55) + 40)
        self.assertEqual(prepared["required_schema"], {"type": "object"})
        self.assertLessEqual(len(prepared["retrieval_context"]["chunks"]), 8)
        self.assertLessEqual(len(prepared["retrieval_context"]["top_chunks"]), 5)

    def test_call_gemini_json_retries_with_fallback_api_version_on_404(self):
        first_error = urllib.error.HTTPError(
            "https://generativelanguage.googleapis.com/v1/models/test:generateContent?key=x",
            404,
            "Not Found",
            hdrs=None,
            fp=None,
        )

        with mock.patch.object(prd_pipeline, "_urlopen_json", side_effect=[first_error, {"candidates": [{"content": {"parts": [{"text": "{\"decision\":\"ACCEPT\"}"}]}}]}]):
            result = prd_pipeline.call_gemini_json(
                "gemini-test",
                "api-key",
                "Return JSON",
                {"x": 1},
            )

        self.assertEqual(result["decision"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
