# Memory Card: extract-intent CLI

Goal:
- give the user one direct CLI for semantic intent extraction over one session file
- also support checkpoint-based summaries for tracked JSON, JSONL, and log files

Tool:
- `tools/extract-intent/extract-intent`
- convenience wrapper: `./scripts/extract-intent`
- global install helper: `./scripts/install_extract_intent_global.sh`

Rules:
- default output is strict JSON
- `--pretty` is the human terminal mode
- use `intent-vector-ru` for session intent and `change-vector-ru` for tracked file deltas
- steps should be 3-7 items and easy to read in Russian
- session intent mode should not echo the source path
- tracked diff mode should always show the tracked path and time window
- `--project` is a thin orchestration mode: first resolve latest session via `nx-collect`, then run normal intent extraction
- `--track` is a checkpoint mode: compare current file against saved baseline, summarize the delta, then advance baseline by default
- `--provider` means source provider
- `--processing-provider` means the AI provider that generates the semantic summary

Terminal view:
- use `①②③④⑤⑥⑦`
- keep the pretty mode compact and glanceable

Examples:

```bash
./scripts/install_extract_intent_global.sh
extract-intent --input /full/path/to/session.jsonl --pretty
extract-intent --project ~/zoo/agents_sessions_dashboard --pretty
extract-intent --project ~/zoo/agents_sessions_dashboard --provider gemini --processing-provider gemini
extract-intent --project ~/zoo/agents_sessions_dashboard --providers codex,claude,gemini,qwen,pi,kimi
extract-intent --track /var/log/app.log --pretty
extract-intent --track /tmp/state.json --track-kind json --ignore-path meta.updated_at
```
