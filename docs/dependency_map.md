### PRD System Dependency Map

### API to Workflow Chain
```text
agent_server.py
  └─ AgentHandler.do_POST
      ├─ /api/agents/run
      │   └─ (agent_id == "prd_pipeline") -> handle_prd_pipeline(...)
      └─ /api/prd/pipeline
          └─ handle_prd_pipeline(...)
              ├─ document_ingestion.ingest_document_payload(...) [optional]
              ├─ resolve_cloud_model_credentials(...) [cloud mode]
              └─ prd_pipeline.run_prd_pipeline(prd_text, PipelineOptions)
```

### PRD Workflow to Agent Stages
```text
prd_pipeline.run_prd_pipeline
  ├─ evaluate_prd_text_quality
  ├─ build_retrieval_context
  ├─ call_structured_agent("prd_analyst")
  │   └─ apply_agent1_quality_gate
  ├─ call_structured_agent("prd_reviewer") [review loop]
  ├─ call_structured_agent("test_designer")
  └─ call_structured_agent("automation_designer")
```

### Provider Helpers Used by PRD Workflow
```text
call_structured_agent
  ├─ call_ollama_json (provider=local)
  │   └─ extract_json -> json.loads -> _validate_agent_response
  └─ call_gemini_json (provider=cloud)
      └─ extract_json -> json.loads -> _validate_agent_response
```

### LLM Provider Stack Used by Active Runtime
```text
prd_pipeline.call_structured_agent
  ├─ call_ollama_json (provider=local)
  └─ call_gemini_json (provider=cloud)

agent_server.call_ollama (standalone non-PRD agent route)

llm_client.LLMClient.generate
  ├─ Groq
  ├─ Gemini
  └─ Ollama
```

### Supporting Modules
- `document_ingestion.py`: input normalization for uploaded documents.
- `cloud_providers.json`: encrypted cloud model/API key registry.
- `encrypt_api_key.py`: utility for generating encrypted config keys.
- `script.js` + `index.html`: UI orchestration and rendering.
- `test_prd_pipeline.py`, `test_agent_server_providers.py`, `test_document_ingestion.py`, `test_llm_client.py`: regression coverage.
