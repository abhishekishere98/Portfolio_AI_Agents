# PRD Pipeline Quickstart

Use this when you want to test the enterprise PRD pipeline quickly.

## Step 1: Start The Server

```powershell
python agent_server.py
```

## Step 2: Create A Sample PRD Request

Use this example PRD:

```text
Product Requirement: Job Alert Dashboard

Goal:
Help job seekers track job posts from multiple sources in one dashboard.

Persona:
Job seeker who applies to AI automation and QA roles.

Features:
1. User can add job source URLs.
2. System checks for new jobs every morning.
3. User can mark jobs as interested, applied, rejected, or saved.
4. Dashboard shows counts by status.
5. User receives an email summary.

Acceptance Criteria:
- User can add, edit, and delete job sources.
- System stores new job posts without duplicates.
- Dashboard updates status counts correctly.
- Email summary is sent once per day.

Demo:
Show adding a job source, running the scan, saving a job, and seeing dashboard counts update.
```

## Step 3: Send The Request

You can use Postman, Insomnia, Thunder Client, or any API tool.

URL:

```text
http://localhost:8787/api/prd/pipeline
```

Method:

```text
POST
```

Body:

```json
{
  "prd_text": "Paste the PRD text here",
  "automation_framework": "playwright",
  "use_llm": true
}
```

If Ollama is not running, set:

```json
"use_llm": false
```

This will use the built-in fallback logic.

## What You Should See

For a good PRD:

```text
status: APPROVED
```

For a bad document:

```text
status: REJECTED
```

If the review loop fails too many times:

```text
status: NEEDS_CLARITY
```

## Framework Choice

For Playwright:

```json
"automation_framework": "playwright"
```

For Selenium:

```json
"automation_framework": "selenium"
```

## How To Read The Output

- `agent_1_prd_structure`: epics, stories, acceptance criteria, personas, demo points.
- `agent_2_review`: quality review and approval/rework result.
- `agent_3_test_design`: component tests, E2E tests, unit tests, PACT tests.
- `agent_4_automation_design`: automation-ready test ideas.
- `audit_log`: what each agent did.
