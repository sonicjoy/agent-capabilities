<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Development workflow

Verification, debugging, local engine restriction, GitLab work items, check knowledge first.

---

## Check Knowledge Before Implementing
**Added**: 2026-02-04
**Updated**: 2026-10-08
**Id**: `check-knowledge-before-implementing`

> Before changing code in documented areas (pools, RemUnits, pool restart, event ordering, conventions), look up the relevant facts with the knowledge skill (kb.py) first.

**Before implementing code changes** that touch areas we've documented (business rules, technical decisions, conventions, architecture, shutdown/controller behavior, pool logic, event ordering), **look up the relevant knowledge first** so the change does not violate them.

Look it up with the `knowledge` skill: `kb.py read search --q "…"`, then `kb.py read fact --id …` for the hits that matter. Check when the change affects: RemUnitsController/shutdown, leg official/completed logic, pool restart or event ordering, coding conventions (e.g. delete over add), or any other topic we've recorded.

`knowledge/colossus-bets/` in agent-capabilities is the generated export of the KB: read it only when no KB login is set up, and never edit it.

---

## Code Verification
**Added**: 2026-01-23
**Id**: `code-verification`

> Verify code changes by building, add unit tests for core logic changes, and run the existing tests.

When making code changes:
1. Always verify changes by building the solution
2. For core logic changes, create unit tests to cover the new behavior
3. Run existing tests to ensure no regressions

---

## Colossus work items for agent tasks
**Added**: 2026-10-05
**Context**: The team asked agents to do this for every Colossus task.
**Id**: `colossus-work-items-for-agent-tasks`

For any Colossus task the agent works, open one GitLab work item on `gitlab.colossusbets.com`, in the project for the repo being changed, assigned to the user you are working for.

Description headings, in this order:

1. **Why** — the problem and who feels it.
2. **What** — the change, in one or two sentences.
3. **Details** — evidence, the rule, and the pieces of work.
4. **Scope** — in, and out.
5. **Acceptance** — how we will know it is done.

Keep that item in sync with the agent's progress in the same turn the progress happens:

- Work starts: status `In progress` and a short progress comment.
- The approach or the result changes: comment. Rewrite the description when Why, What, Details, Scope, or Acceptance changed.
- The work is verified done: comment the evidence, then status `Done`.

Status is the built-in field (`To do`, `In progress`, `Done`), not a label. One work item per task. Do not open a second one.

---

## Debugging Workflow
**Added**: 2026-01-27
**Id**: `debugging-workflow`

> When debugging, verify theories and propose fixes, but don't change code until the user confirms.

When debugging (investigating bugs, tracing behavior):
1. **Analyze and propose** root causes and fixes, but **do not change code** until user explicitly confirms
2. **Verify theories** using available context (DB access, codebase search, logs, schema, sample data) before reporting
3. Report what was verified vs. what remains assumed

Sequence: investigate → verify → explain and suggest fix → **wait for user go-ahead** before implementing.

---

## GitLab Issue Comments
**Added**: 2026-01-28
**Updated**: 2026-10-05
**Id**: `gitlab-issue-comments`

Comments on someone else's GitLab issue still need the user's go-ahead.

For a Colossus task this agent is doing, the work-item rule below replaces that restriction. Create the item and update its status and progress comments as the work moves.

---

## Local Engine Execution Restriction
**Added**: 2026-01-26
**Id**: `local-engine-execution-restriction`

**DO NOT run the engine locally** when working with staging environment. The engine connects to Kafka and processes messages from shared topics, which causes race conditions and duplicate processing that can corrupt pool state and remaining unit calculations.

For debugging, use database queries and code analysis instead of running the engine locally. If runtime debugging is needed, use instrumentation logs or a dedicated test environment with isolated Kafka topics.
