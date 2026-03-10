# Contracts

This project now has an isolated contract layer for CLI tools that work on
JSON and JSONL session logs.

Current contract chain:

```text
CLI flags / request JSON -> session-collect-request -> nx-collect -> session-collect-result
CLI flags / request JSON -> jsonl-cognitive-request -> nx-cognize -> jsonl-cognitive-result
CLI flags / request JSON -> intent-extract-request -> extract-intent -> intent-extract-result
```

Rules:
- `additionalProperties: false` on root objects
- stdout is reserved for contract JSON
- stderr is reserved for diagnostics
- tools in `tools/` must not import `backend/` or `frontend/`

Current contracts:
- `session-collect-request`
- `session-collect-result`
- `jsonl-cognitive-request`
- `jsonl-cognitive-result`
- `intent-extract-request`
- `intent-extract-result`
