### PRD Pipeline Fallback Root Cause Report

### Execution path
- `agent_server.py` → `AgentHandler.do_POST` → `AgentHandler.handle_prd_pipeline`
- `handle_prd_pipeline(...)` calls `prd_pipeline.run_prd_pipeline(...)`
- `run_prd_pipeline(...)` orchestrates:
  - `call_structured_agent("prd_analyst", ...)`
  - `apply_agent1_quality_gate(...)`
  - `call_structured_agent("prd_reviewer", ...)`
  - `call_structured_agent("test_designer", ...)`
  - `call_structured_agent("automation_designer", ...)`

### Failure point
- Original failure happened in `prd_pipeline.call_structured_agent(...)`.
- The function wrapped provider calls in a broad `try/except Exception` and always returned `fallback()` on failure.
- This masked transport/parsing/provider failures and caused deterministic template data to appear as if it came from the LLM path.

### Exception type
- Reproduced runtime failure: `TimeoutError`

### Exception message
- Reproduced message: `timed out`

### Raw model output summary
- In timeout cases: no response payload is returned from the provider call.
- In successful provider calls: model output arrives under:
  - Ollama: `response["message"]["content"]`
  - Gemini: `response["candidates"][0]["content"]["parts"][*]["text"]`

### Validation results
- Previous behavior:
  - Provider exception was swallowed.
  - JSON parsing/validation path was skipped.
  - Deterministic fallback returned hardcoded structures.
- Updated behavior:
  - Provider call failures are logged and raised as `PipelineExecutionError`.
  - Raw output summary, extracted JSON summary, and parsed-key diagnostics are logged.
  - Response shape validation is explicit (`dict` expected) and logged.

### Recommended fix
- Keep silent fallback disabled for LLM mode.
- Restrict fallback to explicit `use_llm=False` mode.
- Keep provider and parsing diagnostics enabled.
- Keep longer Ollama timeout (`300s`) for large PRDs/models.
- Return structured API errors (`pipeline_execution_failed`) to the UI so failures are visible and actionable.
