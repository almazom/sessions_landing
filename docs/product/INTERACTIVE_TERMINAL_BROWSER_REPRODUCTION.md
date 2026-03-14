# Interactive Terminal Browser Reproduction

## Purpose

This guide defines one concrete way to verify whether the browser interactive route behaves like a continuation of a real Codex terminal session.

The target is not only "page opens" or "resume button exists".

The target is this:

1. create a new Codex session in terminal
2. identify the exact `rollout-*.jsonl` artifact
3. open the same session in the browser
4. compare the visible tail with the artifact and terminal result
5. send the next prompt from browser
6. continue the same session from terminal
7. inspect whether browser, terminal, and JSONL stay synchronized

This is the exact parity check for the intended "Codex CLI in the browser" experience.

## Scope

This guide is for a real local Codex session artifact, not a synthetic test fixture.

It is intentionally simple:

- arithmetic prompt
- one browser continuation step
- one terminal resume step
- direct JSONL inspection

If this simple case is not trustworthy, bigger interactive scenarios are not trustworthy either.

## Preconditions

- Codex CLI is installed and authenticated
- Agent Nexus published stack is running
- browser auth for Agent Nexus is working
- the repo root is available at `/home/pets/zoo/agents_sessions_dashboard`

Published URL used in examples:

- `http://107.174.231.22:8888`

## Scenario

Use one single Codex session for all steps.

Suggested exact prompt sequence:

1. terminal: `What is 1 + 2? Reply with only the final integer.`
2. browser: `Add 2 to the previous result. Reply with only the final integer.`
3. terminal resume: `Add 2 to the previous result. Reply with only the final integer.`

The exact wording can vary, but the prompts should be simple enough that result drift is obvious.

## Step 1: Create a new terminal session

Run a new non-ephemeral Codex session and save the final text reply:

```bash
cd /home/pets/zoo/agents_sessions_dashboard
codex exec -o /tmp/codex_terminal_step1.txt "Reply with only the final integer. What is 1 + 2?"
```

Success signal:

- the command exits successfully
- `/tmp/codex_terminal_step1.txt` exists
- the reply is `3`
- a fresh session directory appears under `~/.codex/sessions/`

Failure signal:

- command fails
- output file is missing
- final reply is not a clean arithmetic answer

## Step 2: Identify the exact artifact

Find the newest Codex session artifact created after step 1:

```bash
find ~/.codex/sessions -type f -name 'rollout-*.jsonl' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1
```

Then inspect the tail:

```bash
tail -n 20 /absolute/path/to/the/newest/rollout-file.jsonl
```

Success signal:

- you have one exact artifact path
- the artifact contains the terminal prompt/response from step 1
- the artifact filename can be used to build both detail and interactive browser routes

Failure signal:

- the newest artifact is ambiguous
- the prompt/response cannot be matched to the session you just created

## Step 3: Open the same session in browser

Build the browser URLs from the artifact filename:

- detail: `/sessions/codex/<artifact-filename>`
- interactive: `/sessions/codex/<artifact-filename>/interactive`

Open the interactive route in browser.

Expected behavior:

- the route opens without hiding behind a fake loading shell
- the visible tail or timeline corresponds to the real session artifact
- the route clearly identifies the same session
- the browser experience is dominated by the live activity window, not by a large report shell

Success signal:

- the browser shows the same session context as the terminal artifact

Failure signal:

- wrong session opens
- browser tail does not match the artifact
- route collapses into unrelated dossier-only behavior

## Step 4: Send the next prompt from browser

In the browser composer, send a continuation prompt such as:

`Add 2 to the previous result. Reply with only the final integer.`

Then observe:

- UI response
- network requests
- JSONL file modification time
- JSONL tail after reload
- whether the browser is performing a real continuation or only a local acknowledgement

Checks:

```bash
stat /absolute/path/to/the/newest/rollout-file.jsonl
tail -n 30 /absolute/path/to/the/newest/rollout-file.jsonl
```

Success signal:

- the browser prompt creates a real backend continuation
- the JSONL artifact changes
- the route shows the updated turn
- the next integer is `5`

Failure signal:

- browser only shows local acknowledgement
- no real session artifact update happens
- no new terminal-equivalent turn appears in the JSONL

## Step 5: Resume the same session from terminal

Extract the real session id from the artifact if needed, then run:

```bash
cd /home/pets/zoo/agents_sessions_dashboard
codex exec resume <session-id> -o /tmp/codex_terminal_step2.txt "Add 2 to the previous result. Reply with only the final integer."
```

Success signal:

- terminal resume succeeds
- `/tmp/codex_terminal_step2.txt` exists
- the result advances from the previous terminal result
- the JSONL artifact grows
- if browser step 4 succeeded, terminal result becomes `7`
- if browser step 4 only acknowledged locally, terminal result becomes `5`

Failure signal:

- resume fails
- a different session is resumed
- the artifact does not change

## Step 6: Reload browser and compare again

Reload the same interactive route and compare it with:

- current JSONL tail
- latest terminal reply
- the last integer that the user sees in the browser activity surface

Success signal:

- browser route now reflects the new terminal continuation
- the same session still feels like one shared conversation

Failure signal:

- browser route stays frozen on old state
- browser state diverges from artifact state
- browser and terminal act like separate worlds

## What Counts As A Pass

This flow should be considered truly interactive only if all of these are true:

- terminal-created session is correctly identified in browser
- browser view reflects the same artifact history
- browser prompt causes a real continuation, not just local UI acknowledgement
- terminal resume continues the same session
- JSONL remains the shared source of truth
- browser reload reflects the updated shared state

## What Counts As A Partial Pass

This flow is only partially working if:

- browser can open the right session
- browser can show replay/tail honestly
- terminal resume works
- but browser prompt does not yet write back into the real session runtime

That is useful progress, but it is not yet terminal-like browser interactivity.

## Operator Note

This guide is intentionally stronger than a visual smoke test.

It is designed to catch the exact product mistake where:

- the browser route looks interactive
- the composer accepts text
- but no real session continuation happens underneath

If that happens, the route is still a browser shell over a local mock interaction rather than over the real Codex session.

## Why This Guide Matters

This scenario is the simplest honest bridge between:

- Codex terminal session
- Agent Nexus browser route
- real session artifact

If the system passes this scenario cleanly, it is much closer to the intended "Codex CLI in the browser" experience.

## Observed Run On 2026-03-14

The repository was exercised against this guide on 2026-03-14 with real session artifacts and real browser continuation checks.

Executed proof commands:

```bash
cd /home/pets/zoo/agents_sessions_dashboard
PYTHONPATH=. pytest tests/interactive/test_task_052.py -q
PYTHONPATH=. pytest tests/interactive/test_task_053.py -q
PYTHONPATH=. pytest tests/interactive/test_task_062.py -q
```

Observed result:

- `tests/interactive/test_task_052.py` passed locally
- `tests/interactive/test_task_053.py` passed against the published URL
- `tests/interactive/test_task_062.py` passed for the local live-motion proof

What this confirms:

- browser prompt submit now mutates the real shared Codex artifact
- the browser route receives live `thread`, `turn`, and `agent_message` motion during continuation
- the same session stays aligned across browser view, backend continuation flow, and JSONL artifact growth

Current verdict on 2026-03-14:

- the previously confirmed gap "browser submit is not terminal continuation" is no longer reproduced by these real E2E checks
- the route is materially closer to the intended terminal-like interactive shell
