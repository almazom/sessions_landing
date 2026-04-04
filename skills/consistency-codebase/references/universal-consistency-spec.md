# Universal Consistency Spec

## Purpose

This file defines universal writing, structure, and maintainability rules for agent task and reference markdown files.

Its goal is to keep these files portable across repositories and consistent in tone, terminology, structure, precedence handling, and output contracts.

This file defines editorial rules only. Repository-specific behavior, workflow policy, implementation constraints, and coding preferences belong in project-local instruction files such as `AGENTS.md`, `PROFILE.md`, and `AURA.md`.

## Inputs

These rules apply to:

- agent task specifications
- reference workflows
- review instructions
- reusable prompt-library markdown files

These rules do not replace project policy. They standardize how policy is expressed.

Relevant project instruction files may include:

- `AGENTS.md`
- `PROFILE.md`
- `AURA.md`
- `HIGH_LEVEL_EXPECTATIONS.md`

## Pre-checks

1. Classify the target file as one of these types:
   - universal editorial spec
   - project instruction file
   - task, workflow, review, or prompt-library markdown
2. Decide whether the file should stay universal or should inherit project-local policy.
3. Resolve the applicable instruction sources before editing.
4. If an expected project instruction file does not exist, continue with the remaining applicable files and fall back to this universal consistency file.

Default precedence:

1. The most specific directory-local instruction file
2. The repository-root instruction file
3. This universal consistency file
4. Generic defaults in the task file itself

If instructions conflict:

- State the conflict briefly.
- Follow the most specific applicable instruction.
- If scope is unclear, prefer the rule attached to the files or directories being modified.

## Required Steps

1. Keep universal editorial rules separate from project-specific behavior.
2. Use a strict, repeatable document skeleton unless the document type has a clear reason to omit a section.
3. Make precedence and fallback behavior explicit whenever multiple instruction sources can apply.
4. Treat maintainability as a writing requirement.
5. Use one canonical term for each recurring concept.
6. Use imperative voice, direct formal prose, and concise procedure lists for instructions.
7. Keep behavioral rules in task files and editorial rules in universal consistency documents unless exact wording changes behavior.
8. Keep the file portable by preferring generic labels over repository-specific jargon and by isolating repository-bound examples.

Recommended section order:

1. Purpose
2. Inputs
3. Pre-checks or Preconditions
4. Required steps
5. Validation or Filtering rules
6. Output format
7. Exceptions or Fallback behavior
8. Notes

Maintainability checks:

- avoid duplicated rules that can drift apart
- keep one decision or action per instruction when practical
- define ambiguous terms before reusing them
- keep thresholds, precedence rules, and output contracts in stable dedicated sections
- isolate examples from normative instructions

Terminology rules:

- Use `subagent` consistently. Do not alternate between `agent`, `spawned agent`, and `spawned subagent` unless the distinction is intentional and defined.
- Use `pull request` on first mention, then `PR` if abbreviation improves readability.
- Use `confidence score` for numeric issue evaluation.
- Use exact filenames when referring to governing files such as `AGENTS.md`, `PROFILE.md`, `AURA.md`, or `CLAUDE.md`.
- Do not invent filename variants.

Writing rules:

- Use imperative voice for instructions.
- Use direct, formal prose.
- Avoid slang, shorthand, and conversational spelling.
- Avoid duplicated words and repeated instructions unless repetition is safety-critical.
- Prefer short paragraphs and ordered lists for procedures.
- Keep each instruction focused on one action or decision.
- Define ambiguous terms before using them repeatedly.

## Validation Rules

Revise wording that contains:

- typos in operational instructions
- chat-style shortcuts such as `u`, `pls`, or `w/`
- inconsistent naming for the same concept
- vague modifiers without criteria, such as `simple`, `obvious`, or `important`
- duplicated or contradictory procedural steps
- maintainability debt caused by repeated rules or mixed-purpose paragraphs

Before finalizing a task or reference markdown file, check that:

- the section order is complete and consistent
- all terminology is canonical
- all filenames are exact
- all major decisions have explicit precedence rules
- all thresholds are defined when applicable
- the output format is isolated in its own section when needed
- the file contains no slang, typos, duplicated words, or contradictory steps
- project-specific policy has not leaked into universal guidance
- the file is easier to maintain after the revision than before it

A file should be revised before use if it:

- mixes project-specific policy with universal editorial rules
- uses inconsistent terminology for the same concept
- omits precedence or fallback behavior where multiple instruction sources may exist
- lacks a dedicated output contract when one is needed
- contains obvious grammar, spelling, or formatting issues
- contains duplicated guidance or vague wording that will make future edits inconsistent

## Output Format

Task and reference markdown files should define output contracts like this:

- Include a dedicated `Output format` section or `Example output` section when the workflow produces structured output.
- Place exact templates in fenced code blocks.
- State `Follow this format precisely.` when the format is strict.
- Define each valid output case separately when more than one output is allowed.
- Keep examples separate from normative instructions.

When a workflow uses numeric thresholds or score cutoffs:

- define the scale explicitly
- define what each threshold means
- state what happens above and below the threshold
- keep scoring rules in one section rather than scattering them across the file

## Exceptions

- Project instruction files may add behavioral policy, but they should not replace this file as the universal editorial layer.
- If the repository uses `docs/**/HIGH_LEVEL_EXPECTATIONS.md`, treat the nearest relevant file as a product-expectation overlay rather than as a replacement for root instruction files.
- If a document type does not need every section in the recommended order, keep the remaining sections in order instead of inventing filler text.
- If repository-specific examples are necessary, mark them clearly as examples and keep the normative rule generic.

## Notes

Use this split consistently:

- Put behavioral rules in the task file. These rules state what the agent must do.
- Put editorial rules in a universal consistency file. These rules state how the task file should be written.

Minimal starter template:

````md
# <title>

## Purpose
...

## Inputs
...

## Pre-checks
...

## Required steps
1. ...
2. ...

## Validation rules
...

## Output format
Follow this format precisely.

```text
...
```

## Exceptions
...

## Notes
...
````
