# Memory Card: session-query CLI

Goal:
- give the detail page a safe ask-only query layer over one session artifact

Tool:
- `tools/nx-session-query/nx-session-query`

Rules:
- read one JSON or JSONL artifact file only
- keep stdout as strict JSON by default
- keep stderr diagnostic-only
- do not mutate the source artifact
- answer from local artifact evidence only in the first version

Expected output shape:
- short answer text
- confidence score
- evidence excerpts
- explicit limitations for local lexical matching

Examples:

```bash
tools/nx-session-query/nx-session-query \
  --input /full/path/to/session.jsonl \
  --question "Какая была главная цель этой сессии?"

tools/nx-session-query/nx-session-query \
  --input /full/path/to/session.jsonl \
  --question "Какие файлы обсуждались?" \
  --pretty
```
