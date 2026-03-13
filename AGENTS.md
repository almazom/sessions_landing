# Agent Nexus Agent Instructions

Read this first when working in this repository as an AI coding agent.

## Bootstrap

Read in this order before creating or changing isolated CLI tools:

1. `PROFILE.md`
2. `AURA.md`
3. `PROTOCOL.json`
4. `.MEMORY/00-index.md`
5. Relevant `.MEMORY` cards for the current tool or provider chain
6. `contracts/*.schema.json`
7. `tools/*/MANIFEST.json`

`PROTOCOL.json` is the topology source of truth for isolated contract-first CLI tools.

## Mandatory Bootstrap For New CLI Tasks

For every new isolated CLI task, use this bootstrap scenario as mandatory:

`PROFILE.md -> AURA.md -> PROTOCOL.json -> .MEMORY -> contracts -> MANIFEST`

Interpretation:

- `PROFILE.md`: understand why the task matters
- `AURA.md`: understand how the system should be built
- `PROTOCOL.json`: understand what already exists
- `.MEMORY`: load short reusable operational context
- `contracts`: define or inspect the data boundary
- `MANIFEST`: define or inspect the CLI surface

Rule:

- do not start a new CLI from implementation first
- do not skip directly from idea to `main.py`
- do not treat `tools/` as the source of truth before contracts and manifests exist

Aura layout:

- `AURA.md` is the stable repo entrypoint
- `AURA.md` points to `.aura/latest/AURA.md`
- `.aura/latest` points to the active version directory
- old Aura versions should stay in `.aura/v*/`

Documentation role split:

- `PROFILE.md` answers why the project exists
- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` defines what good product outcomes and UX behavior should look like
- `AURA.md` defines the project method and style through the active `.aura/latest` version
- `PROTOCOL.json` defines topology and contracts
- `.MEMORY` keeps short operational context

## When To Read PROFILE And AURA

Read `PROFILE.md` when you need the bigger product context.

It is especially useful when:

- you are not sure why a feature matters
- you need to decide what information belongs in the private core product
- you need to understand the user, the main problem, or the reason this system exists
- you are making prioritization decisions and need the highest-level goal

Read `docs/product/HIGH_LEVEL_EXPECTATIONS.md` when:

- you need the target product shape, not only the project reason
- you are deciding what belongs on the dashboard versus a session detail page
- you need UX or information-architecture expectations
- you need to judge whether a feature improves narrative clarity or operational evidence

Read `AURA.md` when you need the bigger architectural and methodological context.

It is especially useful when:

- you are deciding whether something should become an isolated CLI
- you are unsure how to structure a new tool, contract, or workflow
- you need the repo style, build order, or system direction
- you need to understand how markdown, contracts, manifests, and tools should work together

Read `.aura/latest/AURA.md` directly when:

- you are updating Aura itself
- you need to inspect the active versioned source rather than the stable symlink
- you want to compare the current Aura with future or older `.aura/v*/` versions

Short rule:

- `PROFILE.md` explains why
- `docs/product/HIGH_LEVEL_EXPECTATIONS.md` explains what good looks like
- `AURA.md` explains how
- `PROTOCOL.json` explains what exists
- `.MEMORY` explains short reusable operational context

## What Exists Now

Current isolated CLI layer:

- `PROFILE.md`
- `AURA.md`
- `.aura/latest/AURA.md`
- `.aura/templates/`
- `.aura/kanban/latest`
- `PROTOCOL.json`
- `contracts/session-collect-request.schema.json`
- `contracts/session-collect-result.schema.json`
- `contracts/jsonl-cognitive-request.schema.json`
- `contracts/jsonl-cognitive-result.schema.json`
- `tools/nx-collect/`
- `tools/nx-cognize/`
- `.MEMORY/06-jsonl-cognitive-cli.md`
- `.MEMORY/07-provider-fallback-chain.md`
- `.MEMORY/08-jsonl-cognitive-contracts.md`
- `.MEMORY/09-session-management-workflow.md`
- `.MEMORY/10-session-collect-cli.md`

Reference implementation:

- `tools/nx-collect/nx-collect`
- `tools/nx-collect/main.py`
- `tools/nx-collect/MANIFEST.json`
- `tools/nx-collect/providers.json`
- `tools/nx-cognize/nx-cognize`
- `tools/nx-cognize/main.py`
- `tools/nx-cognize/MANIFEST.json`
- `tools/nx-cognize/providers.json`

## Isolation Rules

When creating more CLI tools in `tools/`, keep them fully isolated.

- Do not import `backend/`
- Do not import `frontend/`
- Do not depend on app runtime state, HTTP routes, or React components
- Read input only from files or CLI flags
- Write contract JSON only to stdout or an explicit output file
- Write diagnostics only to stderr
- Keep each tool focused on one operation

If a tool needs provider orchestration, make it explicit through a provider chain and preflight rules, not hidden fallback behavior.

## Contract-First Order

Always work in this order:

1. Define or update the contract in `contracts/`
2. Register the contract and tool in `PROTOCOL.json`
3. Create the tool folder in `tools/<tool-name>/`
4. Add `MANIFEST.json`
5. Add the executable wrapper
6. Implement `main.py`
7. Add examples in `contracts/examples/`
8. Add or update `.MEMORY` cards if the workflow is reusable
9. Smoke-test the tool on a real local file

Do not start from implementation first.

## CLI Engineering Mindset

When creating or changing CLI tools in this repository, act as an expert Unix/Linux CLI engineer with deep contract-first discipline.

Working rule:

- think about the contract first
- then think about the CLI surface and flags
- then think about manifest and examples
- only after that implement `main.py` and wrapper details

Implementation is the latest step, not the first step.

For CLI work, prefer:

- simple Unix-shaped commands
- explicit stdin/stdout/stderr behavior
- predictable exit codes
- composable file-oriented operations
- low-level shell literacy when it improves correctness or observability

Do not jump from an idea directly into Python implementation before the contract and CLI boundary are clear.

## Required Tool Shape

Each isolated CLI should have this minimum shape:

```text
tools/<tool-name>/
├── MANIFEST.json
├── <tool-name>        # executable wrapper
├── main.py
└── providers.json     # only if the tool uses provider fallback
```

Recommended contract shape:

```text
contracts/
├── <name>-request.schema.json
├── <name>-result.schema.json
└── examples/
    ├── <name>-request.sample.json
    └── <name>-result.sample.json
```

## How To Create More CLI Tools

Use `tools/nx-cognize` as the starting template.

Good next isolated tools for this repo:

- `tools/nx-filter`: filter normalized sessions by date, provider, cwd, activity state
- `tools/nx-activity`: compute live, active, idle states from timestamps
- `tools/nx-cardify`: render compact card-ready summaries from normalized session JSON

Suggested sequence:

1. Build `nx-activity` on top of normalized session JSON
2. Build `nx-filter` for reusable queries like `today`, `live`, `active_within`
3. Keep `nx-cognize` as the cognitive layer over raw or normalized data

## CLI API Discipline

For every new isolated CLI:

- define input contract version
- define output contract version
- document flags in `MANIFEST.json`
- define exit codes in `MANIFEST.json`
- keep stdout machine-readable
- keep stderr human-readable

Recommended exit code taxonomy:

- `0` success
- `2` invalid arguments or missing input file
- `3` provider or dependency failure
- `4` parse error or contract violation
- `1` unexpected internal error

## .MEMORY Usage

Use `.MEMORY` for short reusable operational knowledge, not as the only source of truth.

Add a new `.MEMORY` card when:

- provider preflight behavior is reusable
- a tool has a reusable fallback chain
- a contract family needs a short operator summary
- there is a stable rule set that an agent should reload quickly next session

Do not move schemas or API truth into `.MEMORY`.

Read a relevant `.MEMORY` card when:

- the task touches published deploy behavior
- the task touches Playwright or browser verification
- the task depends on provider-specific operational rules
- the task needs a short reusable workflow rather than contract truth

## SSOT Kanban Execution

When a working SSOT Kanban JSON exists in `docs/plans/ssot_kanban_*.json`, treat it as the live execution board for the repository.

Core rule:

- the JSON plan is the implementation source of truth
- change task state in the JSON as work advances
- do not leave task progress only in chat messages
- append a `history` entry every time a task changes status
- keep `execution_state` honest while the task is moving

Default per-task flow:

1. Move the next eligible task to `in_progress`
2. Implement the task
3. Run the task-level terminal checks
4. Move the task to `simplification_step`
5. Run the `code-simplifier` skill
6. Move the task to `auto_commit_step`
7. Run the `auto-commit` skill
8. Move the task to `reproduce_step`
9. Run the task's reproduce commands and required browser checks
10. Move the task to `done` only when the real confidence is `>= 95`

Failure handling:

- if reproduction fails, move the task to `failed_reproduction`
- record the failure in `execution_state.last_failure_note`
- return the task to `in_progress` and continue fixing
- if repeated attempts hit the max allowed by the SSOT, move the task to `blocked_needs_human`

Pacing and persistence:

- run the Kanban process continuously task by task
- when an active SSOT Kanban exists, non-stop execution is mandatory until every in-scope card reaches a terminal state
- do not pause the implementation loop after a completed card; immediately advance the next eligible card through the trello-like states in the JSON
- do not stop at planning if implementation is possible
- do not stop at local coding if reproduction or Playwright proof is still missing
- continue until all tasks in the active SSOT are delivered, verified, and moved to terminal states
- the target end condition is all relevant tasks `done` with confidence `>= 95`
- if the user changes scope, update the SSOT first, then continue

Browser, BDD, and published verification:

- major user-facing steps must include terminal reproduction and Playwright verification
- prefer full human-like BDD checks over shallow smoke-only checks
- for interactive routes, use full browser E2E when the SSOT requires it
- for published major steps, follow the published-url flow and do not close work while the live URL is stale or broken

User loop:

- keep the user in the loop with short simplified progress updates
- on major milestones, use the globally available `t2me` CLI to package or relay milestone output
- if the exact usage is unclear, inspect `t2me --help` first
- keep milestone communication compact and operational

## Verification

Before closing work on a new isolated CLI:

1. Run `python3 -m py_compile tools/<tool-name>/main.py`
2. Run the wrapper script on a real local input file
3. Verify fallback behavior with short timeouts if providers are involved
4. Verify the JSON shape matches the declared output contract

## Implementation Session Finish Rule

After each implementation session:

- always run the `code-simplifier` skill before the `auto-commit` skill
- use the `code-simplifier` skill first on the code and docs touched in the session
- use the `auto-commit` skill before closing the session
- run `auto-commit` only after simplification and the relevant verification for the session work are complete
- commit the session-relevant changes when they are in a shippable state
- keep commits atomic
- if the worktree already contains unrelated dirty changes, isolate the session changes instead of sweeping everything into one commit

## Published Deploy Rule

For major app changes, do not stop at local edits or local build output.

Major means changes to:

- visible UI behavior
- frontend routing, hydration, or static assets
- backend routes, auth, or API payloads
- CLI outputs consumed by the app
- `public/` assets, logos, branding, or published runtime scripts

Rule:

- rebuild and republish after major changes
- do not assume the live stack has updated until it is restarted
- before asking the user to test, run the Playwright check yourself first
- when Playwright screenshots are part of user-facing review, send them through `t2me` unless the user explicitly opts out

Required flow:

1. local verification
2. `./scripts/start_published.sh`
3. verify live backend/frontend
4. verify published URL with Playwright

For the detailed deploy/browser checklist, read:

- `.MEMORY/published-url-playwright.md`

Do not close a major UI/runtime task while the published URL is stale, broken, or stuck on loading.

## Current Principle

In this repository, isolated CLI tools are the preferred place for reusable data operations over provider logs.

The app layer may consume them later, but the tool must remain independently runnable and contract-defined from day one.
