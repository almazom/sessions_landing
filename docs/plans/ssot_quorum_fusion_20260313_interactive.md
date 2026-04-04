# SSOT Quorum Fusion Review

Date: 2026-03-13
Board: `docs/plans/ssot_kanban_20260313_062127.json`
Scope: compare SSOT task state against the current interactive-session codebase and proof surface

## Review Setup

This report fuses six parallel review angles:

1. SSOT board integrity
2. Contract and protocol coverage
3. Backend runtime and control coverage
4. Frontend route and UX completion
5. Verification, reproduction, and published proof
6. Security, ownership, reconnect, and operational robustness

The first subagent pass hit a sandbox read failure, so the final quorum was re-run as evidence-only reviews over locally collected file excerpts and board slices.

Local sanity checks run during fusion:

- `python3 -m pytest tests/interactive/test_task_034.py tests/interactive/test_task_035.py tests/interactive/test_task_036.py tests/interactive/test_task_046.py tests/interactive/test_task_049.py tests/interactive/test_task_054.py` -> `12 passed`
- `python3 -m pytest tests/interactive/test_task_038.py` -> failed immediately because the file does not exist

## Quorum Verdict

As of 2026-03-13, the board is not fully done and the interactive initiative is not closed.

The quorum is consistent on three top-level conclusions:

- the SSOT cannot honestly be read as "all tasks done in json"
- the backend has real helper and boot groundwork
- the browser-visible interactive continuation flow is still incomplete and under-proven

## Consensus Findings

### 1. The board is not done, and its integrity is already drifting

Evidence:

- `39` tasks are `done` and `15` tasks are still `backlog`
- open backlog cards include `TASK-037` through `TASK-046` and `TASK-050` through `TASK-054`
- mandatory policy gates still point at backlog cards:
  - major-step reproduce gates at `docs/plans/ssot_kanban_20260313_062127.json:44`
  - browser E2E requirements at `docs/plans/ssot_kanban_20260313_062127.json:56`
  - finalize-delivery requirement at `docs/plans/ssot_kanban_20260313_062127.json:65`

Concrete integrity problems:

- `TASK-053` history says it moved to `in_progress`, but its visible `status` is still `backlog`
- `TASK-054` is still marked `backlog`, but the repo already contains implementation evidence in `tests/interactive/test_task_054.py`

Impact:

- the board does not support an "all done" claim
- the board is no longer a perfectly reliable mirror of repo reality

### 2. Contract-first truth is lagging behind the interactive implementation

Evidence:

- `PROTOCOL.json` only registers the CLI-era contract families and tools
- interactive schemas already exist on disk:
  - `contracts/interactive-runtime-status.schema.json`
  - `contracts/interactive-boot-payload.schema.json`
  - `contracts/interactive-runtime-identity.schema.json`
  - `contracts/interactive-operational-store.schema.json`
- interactive examples also exist under `contracts/examples/`
- backend and frontend already consume the interactive contract surface

Gap:

- interactive contract work appears done in code and SSOT history, but it is still absent from `PROTOCOL.json`

Impact:

- the repository's declared source of truth no longer fully describes the interactive topology
- discoverability and contract governance are weaker than the repo method requires

### 3. Backend progress is real, but still helper-heavy

What is genuinely implemented:

- dedicated backend boot route:
  - `backend/api/routes/sessions.py:481`
- capability gating and route eligibility:
  - `backend/api/session_artifacts.py:668`
- action-envelope validation:
  - `backend/api/interactive_actions.py:140`
- supervisor lock helpers:
  - `backend/api/interactive_supervisor.py:15`
- passing proof slice for implemented cards:
  - `tests/interactive/test_task_034.py`
  - `tests/interactive/test_task_049.py`

What is still missing or only scaffolded:

- boot payload still returns empty placeholder `tail` and `replay`
  - `backend/api/interactive_boot.py:20`
  - `backend/api/interactive_boot.py:73`
- no demonstrated browser-facing control endpoint for `prompt_submit`, `cancel_interrupt`, or `waiting_response`
- no demonstrated dispatch from validated actions into a real runtime continuation loop

Impact:

- the backend can honestly advertise and bootstrap the route
- it does not yet prove a complete browser continuation path

### 4. The frontend is still a shell, not a finished interactive product

Evidence:

- the route mounts only `InteractiveSessionShell`
  - `frontend/app/sessions/[harness]/[id]/interactive/page.tsx`
- the shell explicitly says the final route will replace placeholders
  - `frontend/components/InteractiveSessionShell.tsx:133`
- replay wiring is explicitly "not attached yet"
  - `frontend/components/InteractiveSessionShell.tsx:164`
- composer submit is prevented with no action dispatch
  - `frontend/components/InteractiveSessionShell.tsx:171`
- frontend state helper returns placeholder timeline data and says prompt wiring lands later
  - `frontend/lib/interactive-state.ts:59`
  - `frontend/lib/interactive-state.ts:90`

UX gap called out by quorum:

- no evidence of a dedicated interactive CTA from the session detail page
- this conflicts with the product expectation that a user should be able to go deeper and continue work from the detail page

Impact:

- the route exists visually
- the actual replay-to-live continuation experience is not delivered

### 5. Verification and published proof are far below closure level

Evidence:

- board-required verification cards remain backlog:
  - `TASK-043`
  - `TASK-045`
  - `TASK-050`
  - `TASK-052`
  - `TASK-053`
- expected pytest files for many of those cards do not exist:
  - `tests/interactive/test_task_038.py`
  - `tests/interactive/test_task_043.py`
  - `tests/interactive/test_task_045.py`
  - `tests/interactive/test_task_050.py`
  - `tests/interactive/test_task_052.py`
  - `tests/interactive/test_task_053.py`
- the interactive Playwright spec exists, but every test is skipped:
  - `frontend/e2e/interactive-session.spec.ts:12`
- `tests/interactive/test_task_046.py` only checks a fixture bundle that names those interactive scenarios
  - `tests/interactive/test_task_046.py:13`
- the published URL coverage excerpt proves dashboard/detail/auth/session-artifact behavior, not interactive continuation

Impact:

- there is no credible local browser proof
- there is no credible published interactive proof
- the repo's own verification policy remains unmet

### 6. Security and operational guarantees are only helper-level today

What exists:

- action validation checks actor, thread, owner, and payload shape
  - `backend/api/interactive_actions.py:140`
- auth dependencies exist for HTTP and websocket entry
  - `backend/api/deps.py`
- reconnect and supervisor helper logic exists
  - `backend/api/interactive_reconnect.py`
  - `backend/api/interactive_supervisor.py`

What is still open in the board:

- `TASK-039` session ownership enforcement
- `TASK-040` auth and origin rules
- `TASK-041` resource limits and backpressure
- `TASK-042` lifecycle observability
- `TASK-050` route and security milestone reproduction

Impact:

- security claims must stay qualified
- the current evidence proves safety-oriented helpers, not end-to-end route-bound guarantees

## Positive Signals

The quorum does not claim that nothing was done. These parts are materially real:

- backend interactive boot loader exists and passes its direct tests
- interactive route shell exists
- frontend state scaffold exists
- fixture milestone bundle exists
- runtime control milestone bundle exists
- Codex SDK sidecar probe exists and passes its direct tests

That was confirmed locally by the passing test slice:

- `tests/interactive/test_task_034.py`
- `tests/interactive/test_task_035.py`
- `tests/interactive/test_task_036.py`
- `tests/interactive/test_task_046.py`
- `tests/interactive/test_task_049.py`
- `tests/interactive/test_task_054.py`

## Improvement Order

### Immediate SSOT repair

1. Fix board integrity first:
   - align `TASK-053` visible status with its history
   - decide whether `TASK-054` is still backlog or should move forward in the board
2. Add a simple SSOT consistency check for:
   - status/history mismatch
   - backlog cards with clear shipped evidence
   - done cards missing closure evidence

### Architecture and contract repair

1. Register the interactive contract families in `PROTOCOL.json`
2. Decide whether the interactive surface needs explicit topology registration beyond schemas alone

### Product completion

1. Wire a real browser control path instead of placeholder submit
2. Replace boot payload placeholders with real tail and replay hydration
3. Add the missing detail-page entry CTA and prove the return path

### Verification closure

1. Implement the missing verification cards and their missing pytest files
2. Unskip or replace the interactive Playwright suite with executable real-browser proof
3. Add published interactive-route proof before claiming closure

## Final Assessment

The codebase contains real progress, but it is still in the "bootstrapped scaffold plus backend helpers" phase for interactive continuation.

The strongest single sentence from the quorum is:

> implemented groundwork is real, but the interactive feature is not yet done, and the board should not say or imply otherwise
