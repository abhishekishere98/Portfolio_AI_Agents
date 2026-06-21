from __future__ import annotations

import re
from typing import Any

from agents.common import (
    find_section,
    section_map,
    sentence_case,
    split_items,
    summarize,
)


class PRDAnalyzer:
    name = "Agent 1 - PRD Analyzer"

    def __init__(self, confidence_threshold: int = 70) -> None:
        self.confidence_threshold = confidence_threshold

    def run(self, prd_text: str, feedback: list[str] | None = None) -> dict[str, Any]:
        sections = section_map(prd_text)

        confidence = self._confidence(prd_text, sections)

        if confidence < self.confidence_threshold:
            return {
                "agent": self.name,
                "status": "REJECTED",
                "confidence_score": confidence,
                "message": "Document does not qualify as a software PRD.",
                "reasons": self._rejection_reasons(sections),
            }

        product_name = self._product_name(prd_text, sections)

        business_goal = self._business_goal(sections)

        requirements = find_section(
            sections,
            "feature",
            "requirement",
            "scope"
        )

        acceptance = find_section(sections,"acceptance")

        missing_sections = []

        if not business_goal:
            missing_sections.append("Business Goal")

        if not requirements:
            missing_sections.append("Requirements")

        if not acceptance:
            missing_sections.append("Acceptance Criteria")

        if missing_sections:
            return {
                "agent": self.name,
                "status": "REJECTED",
                "confidence_score": confidence,
                "message": "Document failed PRD validation.",
                "missing_sections": missing_sections,
            }

        personas = self._personas(sections)

        features = self._features(sections)

        dependencies = (
            split_items(
                find_section(
                    sections,
                    "dependencies",
                    "integration"
                )
            )
            or ["Authentication service", "Notification service"]
        )

        risks = (
            split_items(
                find_section(
                    sections,
                    "risks"
                )
            )
            or [
                "Incomplete edge-case requirements",
                "Dependency availability during testing"
            ]
        )

        assumptions = (
            split_items(
                find_section(
                    sections,
                    "assumptions"
                )
            )
            or [
                "Users have valid application access",
                "Core platform services are available"
            ]
        )

        epics = self._epics(
            product_name,
            personas,
            features,
            business_goal,
        )

        if feedback:
            for epic in epics:
                epic["review_feedback_addressed"] = feedback

        return {
            "agent": self.name,
            "status": "VALID_PRD",
            "confidence_score": confidence,
            "product_name": product_name,
            "business_goal": business_goal,
            "personas": personas,
            "features": features,
            "dependencies": dependencies,
            "risks": risks,
            "assumptions": assumptions,
            "epics": epics,
        }

    def _confidence(self, text: str, sections: dict[str, str]) -> int:
        score = 0

        if len(text.strip()) < 300:
            return 0

        business_goal = find_section(
            sections,
            "goal",
            "objective",
            "business"
        )

        requirements = find_section(
            sections,
            "feature",
            "requirement",
            "scope"
        )

        acceptance = find_section(
            sections,
            "acceptance"
        )

        personas = find_section(
            sections,
            "persona",
            "user"
        )

        dependencies = find_section(
            sections,
            "dependency",
            "integration"
        )

        risks = find_section(
            sections,
            "risk"
        )

        if business_goal:
            score += 35

        if requirements:
            score += 35

        if acceptance:
            score += 20

        if personas:
            score += 5

        if dependencies:
            score += 3

        if risks:
            score += 2

        return min(score, 100)

    def _rejection_reasons(self, sections: dict[str, str]) -> list[str]:

        reasons = []

        if not find_section(
            sections,
            "goal",
            "objective",
            "business"
        ):
            reasons.append(
                "Missing Business Goal section."
            )

        if not find_section(
            sections,
            "feature",
            "requirement",
            "scope"
        ):
            reasons.append(
                "Missing Requirements or Features section."
            )

        if not find_section(
            sections,
            "acceptance"
        ):
            reasons.append(
                "Missing Acceptance Criteria section."
            )

        return reasons or [
            "Document does not contain sufficient PRD structure."
        ]

    def _business_goal(self, sections: dict[str, str]) -> str:

        goal = find_section(
            sections,
            "goal",
            "objective",
            "business"
        )

        if not goal:
            return ""

        return summarize(goal, 320)

    def _product_name(self, text: str, sections: dict[str, str]) -> str:

        title = next(
            (
                name
                for name in sections
                if name != "document"
            ),
            "",
        )

        for line in text.splitlines():
            match = re.match(
                r"^\s*#\s+(.+)$",
                line,
            )

            if match:
                return sentence_case(
                    match.group(1)
                    .replace("PRD", "")
                    .strip(" :-")
                )

        return (
            sentence_case(
                title.replace(
                    "prd",
                    ""
                ).strip(" :-")
            )
            or "Software Product"
        )

    def _personas(self, sections: dict[str, str]) -> list[dict[str, str]]:

        raw = find_section(
            sections,
            "persona",
            "user"
        )

        items = split_items(raw)

        return [
            {
                "name": item.split(":")[0].strip(),
                "goal": (
                    item.split(
                        ":",
                        1
                    )[1].strip()
                    if ":" in item
                    else "Complete the product workflow efficiently."
                ),
            }
            for item in items
        ] or [
            {
                "name": "Primary User",
                "goal": "Complete the core product workflow efficiently.",
            }
        ]

    def _features(self, sections: dict[str, str]) -> list[str]:

        raw = find_section(
            sections,
            "feature",
            "requirement",
            "scope"
        )

        return split_items(raw)

    def _epics(self, product_name: str, personas: list[dict[str, str]], features: list[str], business_goal: str,) -> list[dict[str, Any]]:

        primary_persona = personas[0]["name"]

        epics = []

        for index, feature in enumerate(
            features[:4],
            start=1,
        ):

            epic_id = f"EPIC-{index}"

            story_id = f"US-{index}.1"

            title = sentence_case(feature)

            epics.append(
                {
                    "id": epic_id,
                    "title": title,
                    "description": f"Deliver {title.lower()} for {product_name}.",
                    "business_value": business_goal,
                    "target_persona": primary_persona,
                    "demo_scenarios": [
                        f"Demo {primary_persona} completing {title.lower()} successfully.",
                        f"Demo validation or error handling for {title.lower()}.",
                    ],
                    "user_stories": [
                        {
                            "id": story_id,
                            "title": title,
                            "story": f"As a {primary_persona}, I want to {title.lower()} so that I can achieve the product goal.",
                            "priority": (
                                "High"
                                if index <= 2
                                else "Medium"
                            ),
                            "acceptance_criteria": [
                                f"Given a valid {primary_persona}, when the user performs {title.lower()}, then the system completes the action successfully.",
                                f"Given invalid or missing data, when the user performs {title.lower()}, then the system shows a clear validation message.",
                                f"Given the action is complete, when the user reviews the page, then the updated status is visible.",
                            ],
                        }
                    ],
                }
            )

        return epics