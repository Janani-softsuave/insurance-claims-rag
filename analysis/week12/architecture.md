# One-page architecture sketch — Claims Triage & Coverage Assistant

```
 operator
    |
    |  python -m scripts.run_capstone CLM-2027-00310     <- ONE command, ONE entry point
    v
+-------------------------------------------------------------+
|  scripts/run_capstone.py                                     |
|  - builds MCPAgent(system_prompt=CAPSTONE_SYSTEM_PROMPT,      |
|      config_path=mcp_config.capstone.json)                   |
+-------------------------------------------------------------+
    |
    |  agent.connect()  -- reads mcp_config.capstone.json,
    |                      spawns the MCP server as a subprocess,
    |                      calls tools/list -> discovers all 5 tools
    |                      at RUNTIME (none hardcoded in the agent)
    v
+-------------------------------------------------------------+
|  app/mcp_agent/agent.py  (MCPAgent)            <-- AGENT HOP  |
|  - ReAct loop: Gemini generate_content() per iteration         |
|    [MONEY: every iteration here is a billed Gemini call]      |
|  - GeminiKeyRotatingClient: 429/503 retry, hourly wait-loop    |
|  - logs one `generation` span per turn to spans.jsonl,         |
|    tagged with trace_id (captured from get_claim's reply)      |
+-------------------------------------------------------------+
    |  tools/call over stdio (JSON-RPC)           <-- MCP HOP
    v
+-------------------------------------------------------------+
|  app/mcp_servers/capstone_server.py  (subprocess)              |
|  - get_claim        -> mints trace_id, REDACTS PII on write    |
|                         (app.core.tracing.redact), logs span   |
|  - check_coverage_in_force -> in-force vs loss_date            |
|  - search_policy_wording   -> loss-date-scoped retrieval        |
|                         [MONEY: $0 -- local embed + rerank]    |
|  - compute_amounts  -> deductible/sub-limit/policy-limit,       |
|                         kept as 3 distinct numbers              |
|  - refer_to_adjuster -> TERMINAL. Code-enforced: rejects any    |
|                         coverage_signal other than              |
|                         supports_coverage/supports_exclusion/    |
|                         ambiguous, and rejects the literal       |
|                         word "covered" anywhere in the summary. |
+-------------------------------------------------------------+
    |                                    |
    v                                    v
+----------------------+      +--------------------------------+
| app/vectorstore/      |      | analysis/week12/                |
| chroma_store.py        |      |   claims_corpus.json            |
| (date-filtered `where`)|      |   policy_limits.json             |
+----------------------+      |   coverage_in_force.json          |
    |                          +--------------------------------+
    v
 data/raw/exclusions_schedule_2023.md   (effective 2023-01-01 .. 2024-12-31)
 data/raw/exclusions_schedule_2025.md   (effective 2025-01-01 .. current)
 + the existing Week 3-11 policy corpus, untouched

   Both hops append to the SAME file, under the SAME trace_id:
   analysis/week12/spans.jsonl  (stage: generation | retrieval | tools | mcp_tool)
```

**Where the money goes:** the only billed calls are Gemini `generate_content` turns inside
the agent loop (one per ReAct iteration). Retrieval (local embedder + cross-encoder reranker)
and all local tool arithmetic are $0. See `cost_by_stage.md`.

**Where PII stops:** `get_claim`'s MCP response is the only place claimant names/addresses/
injury text ever cross a process boundary, and it's redacted before that boundary, not after.
