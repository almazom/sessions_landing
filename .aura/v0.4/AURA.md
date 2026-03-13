# AURA SYSTEM PROTOCOL v0.4 — Agent Nexus

> **Version:** 0.4
> **Date:** 2026-03-12
> **Project:** Agent Nexus
> **Status:** Active

---

ROLE: Build this system as a markdown-centered, contract-first, isolated CLI architecture.

GOAL: Turn provider session files into clear, reusable artifacts through small tools with explicit contracts.

## 1. VERSIONED AURA LAYOUT

This project uses a versioned `.aura/` structure inspired by the CineTaste v5 pattern.

```text
.aura/
├── latest -> v0.4
├── v0.1/
│   └── AURA.md
├── v0.2/
│   └── AURA.md
├── v0.3/
│   └── AURA.md
├── v0.4/
│   └── AURA.md
├── templates/
│   ├── KANBAN.template.json
│   ├── CONTRACT.template.json
│   └── MANIFEST.template.json
└── kanban/
    ├── KANBAN-2026-03-10-bootstrap.json
    └── latest -> KANBAN-2026-03-10-bootstrap.json
```

Stable entrypoints:

- `AURA.md` -> `.aura/latest/AURA.md`
- `.aura/latest/AURA.md` -> current active Aura version

Rule:

- when Aura changes materially, create a new `.aura/vX.Y/` version instead of silently overwriting the pattern
- keep `AURA.md` as the stable path that points to the active version

## 2. SOURCE ORDER

Read and use the project layers in this order:

1. `PROFILE.md` — why the project exists
2. `AURA.md` — how the project should be built
3. `PROTOCOL.json` — topology and contract registry
4. `.MEMORY/` — short operational context
5. `contracts/*.schema.json` — strict data boundaries
6. `tools/*/MANIFEST.json` — executable CLI interfaces

## 3. CORE STYLE

This repository should prefer:

- markdown-centric planning and documentation
- contract-first design
- isolated CLI tools in `tools/`
- explicit provider fallback chains
- small, testable, inspectable artifacts
- feedback-driven, self-verified iteration for integrated and user-visible changes

Avoid:

- hidden runtime coupling
- undocumented magic behavior
- backend/frontend imports inside isolated tools
- mixed stdout diagnostics and JSON payloads
- broad tools with multiple responsibilities

## 4. ISOLATED CLI RULE

New reusable operations should default to isolated CLIs.

Each CLI in `tools/` should:

- own one responsibility
- declare input and output contracts
- expose a clear wrapper command
- be runnable without the web app
- read from files and flags, not app internals
- write JSON to stdout or an explicit output file
- write diagnostics to stderr

If a provider chain is involved, preflight and fallback behavior must be explicit in files, manifests, docs, and state cache.

## 5. CONTRACT-FIRST BUILD ORDER

Build in this order:

1. define the problem boundary in markdown
2. define the contract in `contracts/`
3. register it in `PROTOCOL.json`
4. create `tools/<tool-name>/MANIFEST.json`
5. add the executable wrapper
6. implement `main.py`
7. add examples and smoke tests
8. only then connect it to app-level surfaces if needed

## 6. MARKDOWN-CENTERED DISCIPLINE

Markdown is part of the operating system of the repo.

Use markdown files to keep concerns separate:

- `PROFILE.md` answers why
- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` defines product-level expectations and UX target state
- `AURA.md` defines style and method
- `AGENTS.md` tells agents how to work in this repo
- `.MEMORY/` stores short reusable operational notes
- `README.md` explains setup and usage

## 7. PREFERRED SYSTEM DIRECTION

The preferred direction is a library of isolated tools over provider session files, for example:

- collect
- normalize
- filter
- compute activity
- cognize
- cardify
- publish selected fragments

The web application may consume these tools, but should not be the place where their core logic is born.

## 8. QUALITY BAR

Every new CLI should be:

- easy to run from a documented command example
- easy to test on a real local file
- easy to replace without breaking contracts
- easy to inspect through its manifest and schema

## 9. IMPLEMENTATION SESSION FINISH STYLE

Preferred repo style after each implementation session:

- run the `code-simplifier` skill over the code and docs touched in that session
- keep the simplification pass behavior-preserving
- after simplification and verification, run the `auto-commit` workflow for the changes from that session
- do not leave implementation-session changes uncommitted when they are in a shippable state
- keep commits atomic
- do not sweep unrelated dirty worktree changes into the session commit

Interpretation:

- simplification comes before commit
- verification comes before commit
- auto-commit should package the session work cleanly
- if the worktree already contains unrelated edits, isolate the session-relevant changes instead of committing everything together

## 10. AUTONOMOUS FEEDBACK-DRIVEN FULL-CIRCLE ITERATION

Preferred working style for substantial implementation tasks:

- first recover expectation from the strongest available sources
- recover user intent from the current user request and nearby task context
- derive SDD-like requirements by filling the gaps between expectation, user intent, and the current implementation
- think in terms of a full end-to-end iteration loop, not a one-shot patch

Expectation recovery order:

1. user request
2. `PROFILE.md`
3. `docs/product/HIGH_LEVEL_EXPECTATIONS.md`
4. relevant roadmap docs
5. current code and tests

Autonomous loop:

1. state the likely human workflow for the task as a short step list
2. treat that list as the operational script a human would run in another terminal
3. execute the steps through terminal and built-in tools one by one where safe
4. collect feedback from build output, tests, linters, API responses, browser checks, screenshots, and runtime logs
5. compare that feedback against user intent and expected product behavior
6. identify the remaining gaps
7. iterate again without waiting for the user when the next step is clear and safe

Measurement rule:

- use collected feedback as the measurement layer between expected result, intended result, and actual result
- keep iterating until the result is roughly `95%+` aligned with user intent and product expectation, or until a real blocker is reached
- if the loop cannot safely continue, surface the blocker clearly instead of pretending the task is done

Verification rule:

- for major user-visible, integrated, or published changes, run the full feedback-driven end-to-end circle yourself before inviting the user to test
- prefer `2-3` full runs when the flow crosses frontend, backend, routing, auth, published deployment, or asynchronous behavior
- use each run to collect new feedback, adjust the implementation, and rerun until the flow is stable enough to hand to the user
- do not ask the user to do the first serious validation pass when you can execute that pass yourself
- for docs-only, contract-only, or narrow isolated-CLI changes, use the narrowest sufficient verification instead of forcing browser E2E every time

Communication rule:

- keep the user informed on major steps only
- prefer concise milestone updates over constant narration
- when remote notification is useful, `t2me` is available as a global CLI for Telegram delivery
- use the `t2me` CLI to keep the user informed on major steps, screenshots, or proof artifacts when that improves the workflow

Safety boundary:

- this loop is for safe, evidence-driven iteration, not blind autonomy
- do not invent missing requirements when stronger repo or user context exists
- do not run destructive or high-risk actions just to satisfy the loop
- if credentials, approvals, external side effects, or ambiguous product choices block safe continuation, stop and surface the decision point

## 11. VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| v0.4 | 2026-03-12 | Added self-verified E2E loop guidance and explicit `t2me` major-step notification rule |
| v0.3 | 2026-03-12 | Added autonomous feedback-driven full-circle iteration guidance and `t2me` notification preference |
| v0.2 | 2026-03-12 | Added post-implementation simplification and auto-commit style rules |
| v0.1 | 2026-03-10 | Introduced versioned Aura layout, templates, and stable symlink entrypoint |
