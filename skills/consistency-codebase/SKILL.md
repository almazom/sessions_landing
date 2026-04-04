---
name: consistency-codebase
description: Apply a consistent editorial and structural standard to instruction, workflow, review, and reusable prompt-library markdown files across a repository. Use when creating, reviewing, or normalizing repository guidance files, especially when multiple instruction sources may conflict or when a codebase needs consistent task-file structure, terminology, precedence, maintainability, and output contracts.
---

# Consistency Codebase

## Purpose

Use this skill for markdown governance work. It applies to `AGENTS.md`, `PROFILE.md`, `AURA.md`, task specifications, workflow references, review instructions, and reusable prompt-library markdown files.

Default scope is markdown guidance files only. Do not apply these rules to source code unless the user explicitly expands the task beyond documentation consistency.

## Inputs

- target files or target directories
- repository instruction files if present: `AGENTS.md`, `PROFILE.md`, `AURA.md`
- expectation files if present: exact `HIGH_LEVEL_EXPECTATIONS.md` files under `docs/`
- directory-local `AGENTS.md` files relevant to the affected paths
- user constraints such as review-only, edit-in-place, or universal reusable output

## Pre-checks

1. Identify the affected files.
2. Classify each file as one of:
   - universal editorial spec
   - project instruction file
   - task, workflow, review, or prompt-library markdown
3. Discover governing instruction files per target path in this order:
   - nearest directory-local `AGENTS.md`
   - parent-directory `AGENTS.md` files while walking upward
   - repository-root `AGENTS.md`
   - repository-root `PROFILE.md`
   - nearest relevant `HIGH_LEVEL_EXPECTATIONS.md` under `docs/` when the target is product, UX, roadmap, plan, or other expectation-driven markdown
   - repository-root `AURA.md`
4. If the task spans multiple directories, resolve instructions per file path instead of assuming one global scope.
5. If the file is intended to stay universal, keep project-specific policy out of it.

## Required Steps

1. Read the target file and only the minimum governing instruction files needed for its scope.
2. Normalize terminology so one canonical term is used for each recurring concept.
3. Normalize structure to the standard section order when the document type supports it:
   1. Purpose
   2. Inputs
   3. Pre-checks or Preconditions
   4. Required steps
   5. Validation or Filtering rules
   6. Output format
   7. Exceptions or Fallback behavior
   8. Notes
4. Keep behavioral rules in task or workflow files. Keep editorial rules in universal consistency references.
5. Make precedence explicit wherever multiple instruction sources can apply.
6. Add or tighten the output contract. If the format is strict, state `Follow this format precisely.` and place templates in fenced code blocks.
7. Improve maintainability by removing duplicated guidance, isolating examples from normative instructions, and keeping each instruction focused on one action or decision.
8. Preserve project-specific policy in project-local files instead of moving it into universal guidance.
9. If the user asked for review only, report issues without editing files.

## Validation Rules

Mark the result as `blocked` if any of the following are true:

- conflicting instructions appear without a precedence rule
- a task or workflow file lacks a usable output format
- terminology shifts meaning across the document
- project-specific policy is embedded in a universal consistency file
- the workflow cannot be followed because inputs, preconditions, or fallback behavior are missing

Mark the result as `revise` if the file is usable but still has clarity or maintainability gaps such as:

- duplicated instructions
- weak or inconsistent section order
- vague modifiers without criteria
- mixed behavioral and editorial rules
- examples blended into normative instructions
- unnecessary verbosity that makes future edits harder

Mark the result as `pass` only when the file is structurally consistent, uses canonical terms, has an explicit precedence model where needed, contains a usable output contract, and is easier to maintain after the edit than before it.

## Maintainability Lens

Treat maintainability as a first-class quality dimension.

Check for:

- duplicated guidance that can drift over time
- overlapping sections that split one rule across many places
- vague wording that forces future reinterpretation
- unnecessary repository-specific detail in universal files
- missing decision rules that make future edits inconsistent

Prefer smaller, composable rules over long mixed-purpose paragraphs.

## Output Format

Follow this format precisely.

```text
Result: pass | revise | blocked
Mode: review-only | edited
Scope:
- <path or directory>
Files changed:
- <path or none>
Applied precedence:
- <path>: <resolved instruction sources in order>
Blocking issues:
- <issue or none>
Maintainability issues:
- <issue or none>
Notes:
- <brief note>
```

## Exceptions

- If a target file is not an instruction or workflow markdown file, apply only the terminology, clarity, and maintainability checks that still make sense.
- If a repository has no `AGENTS.md`, `PROFILE.md`, `AURA.md`, or `HIGH_LEVEL_EXPECTATIONS.md`, continue with the remaining applicable instruction files.
- If two same-scope files conflict and neither is more specific, note the conflict briefly and choose the rule closest to the modified file path.
- If the user asks for a universal file, use `references/universal-consistency-spec.md` and keep repository overlays out of the result.
- If the user asks to apply this skill to code, clarify whether they want documentation normalization, naming cleanup, or broader refactoring before changing source semantics.

## Notes

- Read `references/universal-consistency-spec.md` when creating or revising a universal consistency document.
- Do not invent filename variants for governing files.
- Use exact filenames such as `AGENTS.md`, `PROFILE.md`, and `AURA.md`.
- Prefer direct formal prose and ordered lists for procedures.
- When this skill is active, make that visible in the user-facing trace:
  - Emit `⬜⬜⬜ [skill:consistency-codebase] ON ...` in commentary before substantial work begins.
  - Prefix meaningful progress updates tied to this skill with `⬜ [skill:consistency-codebase] STEP ...`.
  - End with `⬜⬜⬜ [skill:consistency-codebase] DONE ...` in the final response or last relevant commentary update.
  - Keep these trace lines short and tied to actual normalization or review work.
