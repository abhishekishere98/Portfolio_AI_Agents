# Enterprise PRD To QA RAG Framework

This framework is designed for this flow:

```text
User gives PRD extract
    |
    v
Agent 1 checks if it is a real PRD
    |
    v
Agent 1 creates epics, user stories, acceptance criteria, personas, and demo points
    |
    v
Agent 2 reviews Agent 1 output
    |
    v
If review fails, Agent 1 reworks it
    |
    v
After 3 failed review loops, stop safely and ask for a better PRD
    |
    v
Agent 3 creates component tests, E2E tests, unit test needs, and PACT contract test suggestions
    |
    v
Agent 4 creates Playwright or Selenium automation-ready test cases
```

## Why This Is Better Than Simple Agents

Simple agents usually answer directly from a prompt.

This framework uses a pipeline:

- Each agent has a clear job.
- Output is structured JSON.
- Agent 2 reviews Agent 1 before moving forward.
- The loop stops after 3 tries so it does not run forever.
- Bad documents are rejected early.
- Test cases trace back to user stories and epics.
- Automation output can target Playwright or Selenium.
- Alumnium is suggested as an optional AI-assisted automation layer.

## Current Files

- `prd_pipeline.py` - main enterprise pipeline.
- `agent_server.py` - exposes the API endpoint.
- `agents.json` - simple portfolio agents from the earlier version.
- `ENTERPRISE_RAG_FRAMEWORK.md` - this architecture guide.

## API Endpoint

Start the server:

```powershell
python agent_server.py
```

Send a PRD request:

```http
POST http://localhost:8787/api/prd/pipeline
Content-Type: application/json

{
  "prd_text": "Paste PRD extract here",
  "automation_framework": "playwright",
  "use_llm": true
}
```

Use Selenium instead:

```json
{
  "prd_text": "Paste PRD extract here",
  "automation_framework": "selenium",
  "use_llm": true
}
```

## Output Sections

When the PRD is good, the API returns:

- `status`: `APPROVED`
- `agent_1_prd_structure`
- `agent_2_review`
- `agent_3_test_design`
- `agent_4_automation_design`
- `audit_log`

When the document is not a PRD, it returns:

- `status`: `REJECTED`
- rejection reasons
- missing information

When Agent 2 asks for too much rework, it returns:

- `status`: `NEEDS_CLARITY`
- reason
- audit log

## Agent Responsibilities

### Agent 1: PRD Analyst

Agent 1 checks:

- Is this actually a PRD?
- What is the product goal?
- Who are the users?
- What epics should exist?
- What user stories should exist?
- What acceptance criteria belong to each story?
- What can be demoed?
- What assumptions and risks exist?

If the document is not a PRD, Agent 1 rejects it.

### Agent 2: PRD Reviewer

Agent 2 checks Agent 1's work.

It reviews:

- Are epics accurate?
- Are user stories testable?
- Are acceptance criteria measurable?
- Are demo points really demoable?
- Are personas clear?

If the quality is poor, it sends feedback to Agent 1.

The loop can happen only 3 times.

### Agent 3: Test Designer

Agent 3 writes:

- Component-level test cases for user stories.
- E2E system-level tests for epics.
- Must-have unit tests.
- PACT contract test suggestions between components.
- Traceability matrix.

### Agent 4: Automation Designer

Agent 4 creates automation-ready test cases for:

- Playwright
- Selenium

It also suggests where Alumnium can be used.

Alumnium should be used as an assistant layer for high-level actions and checks, not as the only source of truth for critical regression tests.

## RAG Design

The current implementation has a simple local retrieval baseline:

- It chunks the PRD text.
- It scores chunks using PRD-related keywords.
- It passes top chunks as retrieval context.

For enterprise production, replace this with:

- Document upload.
- Chunking by section.
- Embeddings.
- Vector database.
- Reranking.
- Citations.
- Prompt grounding rules.

Recommended production tools:

- ChromaDB for simple local vector search.
- Qdrant for stronger production vector search.
- PostgreSQL for run history and traceability.
- Object storage for uploaded documents.

## Enterprise Features To Add Next

1. Store every pipeline run in a database.
2. Add user login.
3. Add document upload.
4. Add vector search.
5. Add UI for PRD pipeline runs.
6. Export output as Markdown, JSON, Excel, and Jira-ready CSV.
7. Add Jira integration.
8. Add test management integration.
9. Add approval workflow for BA, QA, and Product Owner.
10. Add evaluation tests for agent output quality.

## Same Repo Or Separate Repo?

Recommended now: keep it in the same repo as a monorepo-style project.

Reason:

- You are still shaping the product.
- The frontend and backend are changing together.
- It is easier to demo.
- It is easier to keep docs, UI, and pipeline aligned.

Split into separate repos later when:

- The PRD pipeline becomes a standalone product.
- Multiple apps need to call the same backend.
- You need separate deployment teams or release cycles.
- The backend grows into a real platform with auth, database, queues, and integrations.

Suggested future split:

```text
portfolio-site/
prd-rag-platform/
prd-rag-sdk/
```

For now:

```text
ai-agent-portfolio/
  index.html
  script.js
  styles.css
  agent_server.py
  prd_pipeline.py
  docs
```

## Alumnium Notes

Alumnium is useful because it works on top of Playwright, Selenium, and Appium. Its docs describe it as a high-level testing layer that can perform actions, check verifications, and get data from the application state.

Use it for:

- High-level exploratory actions.
- AI-assisted validation.
- Reducing repeated automation code.
- Tests where accessible labels and page structure are strong.

Do not use it alone for:

- Financially critical workflows.
- Security-sensitive checks.
- Contract validation.
- Deterministic unit and API tests.

Keep deterministic assertions for important flows.

Sources:

- Alumnium overview: https://alumnium.ai/docs/
- Alumnium installation: https://alumnium.ai/docs/getting-started/installation/
- Alumnium Playwright guide: https://alumnium.ai/docs/writing-first-test/playwright/
- Alumnium self-hosting guide: https://alumnium.ai/docs/guides/self-hosting/
