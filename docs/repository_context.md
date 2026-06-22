### Project Purpose
- This system turns raw product requirements input (`text` or uploaded document) into structured QA artifacts through a multi-agent workflow.
- It solves the handoff gap between PRD writing and test/automation planning by producing reviewable JSON outputs for each stage.

### High-Level Architecture
- Entry points:
  - `agent_server.py` HTTP API (`/api/agents/run`, `/api/prd/pipeline`, `/api/runtime/options`)
  - `run_prd_workflow.py` for local script execution.
- Agent navigation/runtime metadata source:
  - `agents.json` centralized registry (categories, agent metadata, provider visibility).
- Main PRD execution path:
  - API payload normalization + ingestion
  - `prd_pipeline.run_prd_pipeline(...)`
  - Agent 1 analysis → Agent 2 review loop → Agent 3 test design → Agent 4 automation design
  - API response enrichment (provider/document metadata)

### Agent Responsibilities
- Registry categories used by UI: `requirements`, `testing`, `quality`, `automation`.
- Standalone agents are registry-driven from `agents.json`; disabled agents are hidden from UI and omitted from API list payloads.
- Agent 1 (`prd_analyst`): decides PRD validity and builds structured requirement model (`status`, product info, personas, epics, stories, acceptance criteria, assumptions, risks). Generic/template epic titles are explicitly forbidden.
- Agent 2 (`prd_reviewer`): reviews Agent 1 output for ambiguity, missing requirements, missing acceptance criteria, and testability; returns `APPROVED` or `REWORK_REQUIRED`.
- Agent 3 (`test_designer`): transforms approved PRD structure into validated story-level and epic-level tests plus traceability matrix.
- Agent 4 (`automation_designer`): converts test design into framework-specific automation suites and CI guidance.
- Agent 5: folded into active runtime as the automation-generation stage in `prd_pipeline.py` (`automation_designer`).

### Data Flow
- Inputs:
  - `prd_text` or `uploaded_file` (`filename`, `content_base64`)
  - execution options (`automation_framework`, `use_llm`, `provider`, `cloud_model`)
- Outputs:
  - pipeline status (`REJECTED`, `NEEDS_CLARITY`, `APPROVED`)
  - agent section payloads (`agent_1_prd_structure`, `agent_2_review`, `agent_3_test_design`, `agent_4_automation_design`)
  - `audit_log`, provider metadata, and normalized document metadata.
- JSON contracts:
  - `prd_pipeline.py`: Pydantic models validate every active agent stage (`Agent1*`, `Agent2ReviewModel`, `Agent3TestDesignModel`, `Agent4AutomationDesignModel`)
  - API response shape remains stable for frontend/server (`agent_1_prd_structure`, `agent_2_review`, `agent_3_test_design`, `agent_4_automation_design`)

### Provider Layer
- Supported providers: `Ollama`, `Gemini`, `Groq`.
- Generic cross-agent client: `llm_client.py` (`LLMClient.generate(prompt)`).
- Selection order in `LLMClient`: `Groq -> Gemini -> Ollama` with fallback on failure.
- UI provider visibility is config-driven from `agents.json`; local/Ollama is intentionally disabled in V1 UI while backend support remains.
- PRD pipeline provider path (`prd_pipeline.py`):
  - `provider="local"` → `call_ollama_json`
  - `provider="cloud"` → `call_gemini_json`
  - explicit errors raised when provider/parsing/validation fails in LLM mode.

### Known Issues
- Active production workflow is `prd_pipeline.py`; legacy duplicate workflow folders were removed to prevent drift.
- Agent 1 quality gate can reject poor extraction even when provider call succeeds; this is expected behavior.
- Prompt/schema versioning are static constants; no runtime prompt registry/version tags yet.

### Important Files
- `agent_server.py`: API entrypoint and request routing; called by browser UI and scripts.
- `agents.json`: centralized registry for grouped agent navigation and provider visibility controls.
- `prd_pipeline.py`: active PRD orchestration path used by `/api/prd/pipeline` and `prd_pipeline` agent run mode.
- `document_ingestion.py`: normalized extraction from `PDF/DOCX/TXT/MD` before pipeline processing.
- `llm_client.py`: provider abstraction with fallback order.
- `script.js`: frontend payload construction, provider/agent selection, result rendering.
- `cloud_providers.json`: encrypted cloud model key registry.

### Troubleshooting Guide
- Pipeline execution errors:
  - For LLM mode, inspect `pipeline_execution_failed` API errors (provider call, JSON parse, or schema validation).
  - `prd_pipeline.py` no longer silently falls back to deterministic template outputs in active flow.
- Timeout failures:
  - Ollama timeout in PRD pipeline is `300s` (`OLLAMA_CHAT_TIMEOUT_SECONDS`).
  - Verify model availability at `OLLAMA_URL` and model pull status.
- JSON parsing failures:
  - Inspect logs for `RAW_LLM_RESPONSE`, `EXTRACTED_JSON`, `PARSED_RESPONSE`.
  - Ensure model prompt returns a single JSON object.
- Validation failures:
  - Check `VALIDATION_RESULT` logs for stage-specific schema violations.
  - Ensure model response keys match active Pydantic contracts in `prd_pipeline.py`.

### Future Improvements
- Replace keyword baseline retrieval with embedding/vector retrieval and citation confidence scoring.
- Introduce prompt versioning and response metadata (`prompt_version`, `schema_version`, provider trace ID).
- Add structured retry policies by failure class (timeout vs parse vs schema mismatch) with bounded backoff.

### AI Handoff Summary
#### Paste this section into a new AI chat
- Active API path is `agent_server.py -> handle_prd_pipeline -> prd_pipeline.run_prd_pipeline`.
- Current root-cause fix: LLM-mode failures no longer silently fall back; they raise `PipelineExecutionError` and return `pipeline_execution_failed`.
- Key files to inspect first: `agent_server.py`, `prd_pipeline.py`, `document_ingestion.py`, `llm_client.py`, `script.js`.
- Known risk: provider/model runtime availability (timeouts and remote model schema drift).
- Current diagnostics available in logs: `PROVIDER_CALL_FAILED`, `RAW_LLM_RESPONSE`, `EXTRACTED_JSON`, `PARSED_RESPONSE`, `VALIDATION_RESULT`.
