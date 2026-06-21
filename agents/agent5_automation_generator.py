from __future__ import annotations

from typing import Any

from agents.common import slug
from agents.llm import call_structured_json


class AutomationGenerator:
    name = "Agent 5 - Automation Generator"

    SYSTEM_PROMPT = """You are an automation framework expert.
Given approved requirements, selected epic-level tests, and framework choice, return strict JSON with keys:
- automation_scope: string
- selected_tests: array
- files: object mapping relative file paths to file contents
Generate realistic starter automation files for the requested framework only (playwright or selenium)."""

    def run(self, approved_requirements: dict[str, Any], test_design: dict[str, Any], framework: str) -> dict[str, Any]:
        framework = framework.lower().strip()
        if framework not in {"playwright", "selenium"}:
            raise ValueError("framework must be 'playwright' or 'selenium'")
        high_priority = [
            test for test in test_design["epic_level_tests"] if test.get("priority") == "High"
        ][:3]
        try:
            llm_output = call_structured_json(
                self.SYSTEM_PROMPT,
                {
                    "approved_requirements": approved_requirements,
                    "selected_tests": high_priority,
                    "framework": framework,
                },
            )
            files = llm_output.get("files") if isinstance(llm_output.get("files"), dict) else {}
            if files:
                return {
                    "agent": self.name,
                    "framework": framework,
                    "automation_scope": llm_output.get(
                        "automation_scope",
                        "High priority journeys and critical business flows only.",
                    ),
                    "selected_tests": llm_output.get("selected_tests", high_priority),
                    "files": files,
                }
        except Exception:
            pass

        if framework == "playwright":
            files = self._playwright_files(approved_requirements, high_priority)
        else:
            files = self._selenium_files(approved_requirements, high_priority)
        return {
            "agent": self.name,
            "framework": framework,
            "automation_scope": "High priority journeys and critical business flows only.",
            "selected_tests": high_priority,
            "files": files,
        }

    def _playwright_files(self, requirements: dict[str, Any], tests: list[dict[str, Any]]) -> dict[str, str]:
        product = slug(requirements["product_name"])
        test_methods = []
        for test in tests:
            name = slug(test["title"])
            test_methods.append(
                f"""
def test_{name}(page, app):
    app.login_as_primary_user()
    app.open_feature()
    app.complete_core_workflow()
    app.expect_success_status()
"""
            )
        return {
            f"automation/playwright/test_{product}_critical_flows.py": f'''from pages.{product}_page import {self._class_name(product)}Page


class AppSteps:
    def __init__(self, page):
        self.page = page
        self.feature = {self._class_name(product)}Page(page)

    def login_as_primary_user(self):
        self.page.goto("https://example-app.local/login")
        self.page.get_by_label("Email").fill("user@example.com")
        self.page.get_by_label("Password").fill("Password123!")
        self.page.get_by_role("button", name="Sign in").click()

    def open_feature(self):
        self.feature.open()

    def complete_core_workflow(self):
        self.feature.complete_required_fields()
        self.feature.submit()

    def expect_success_status(self):
        self.feature.expect_success()


def test_data():
    return {{"name": "MVP Demo", "description": "Critical business flow"}}


def app(page):
    return AppSteps(page)
{''.join(test_methods)}
''',
            f"automation/playwright/pages/{product}_page.py": f'''from playwright.sync_api import expect


class {self._class_name(product)}Page:
    def __init__(self, page):
        self.page = page

    def open(self):
        self.page.get_by_role("link", name="Dashboard").click()
        self.page.get_by_role("link", name="Create").click()

    def complete_required_fields(self):
        self.page.get_by_label("Name").fill("MVP Demo")
        self.page.get_by_label("Description").fill("Critical business flow")

    def submit(self):
        self.page.get_by_role("button", name="Submit").click()

    def expect_success(self):
        expect(self.page.get_by_text("Success")).to_be_visible()
''',
        }

    def _selenium_files(self, requirements: dict[str, Any], tests: list[dict[str, Any]]) -> dict[str, str]:
        product = slug(requirements["product_name"])
        test_methods = []
        for test in tests:
            name = slug(test["title"])
            test_methods.append(
                f"""
def test_{name}(driver):
    page = {self._class_name(product)}Page(driver)
    page.login_as_primary_user()
    page.open()
    page.complete_required_fields()
    page.submit()
    page.expect_success()
"""
            )
        return {
            f"automation/selenium/test_{product}_critical_flows.py": f'''from pages.{product}_page import {self._class_name(product)}Page
{''.join(test_methods)}
''',
            f"automation/selenium/pages/{product}_page.py": f'''from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class {self._class_name(product)}Page:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)

    def login_as_primary_user(self):
        self.driver.get("https://example-app.local/login")
        self.driver.find_element(By.CSS_SELECTOR, "[aria-label='Email']").send_keys("user@example.com")
        self.driver.find_element(By.CSS_SELECTOR, "[aria-label='Password']").send_keys("Password123!")
        self.driver.find_element(By.XPATH, "//button[normalize-space()='Sign in']").click()

    def open(self):
        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Dashboard"))).click()
        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Create"))).click()

    def complete_required_fields(self):
        self.driver.find_element(By.CSS_SELECTOR, "[aria-label='Name']").send_keys("MVP Demo")
        self.driver.find_element(By.CSS_SELECTOR, "[aria-label='Description']").send_keys("Critical business flow")

    def submit(self):
        self.driver.find_element(By.XPATH, "//button[normalize-space()='Submit']").click()

    def expect_success(self):
        self.wait.until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Success')]")))
''',
        }

    def _class_name(self, value: str) -> str:
        return "".join(part.capitalize() for part in value.split("_"))
