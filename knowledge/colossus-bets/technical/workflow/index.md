<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Workflow Knowledge Index

Development workflow and process rules.

**Last Updated**: 2026-10-08

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [filtering-data-backend-check.md](filtering-data-backend-check.md) | Filtering data: confirm backend support | 2026-02-04 | - | Check with the user whether filtering needs backend changes. |
| [workflow.md](workflow.md) | Development workflow | 2026-01-23 | 2026-10-08 | Verification, debugging, local engine restriction, GitLab work items, check knowledge first. |

## Quick Reference
- filtering data: filtering-data-backend-check.md - When the user asks to filter data (e.g. by source, date range, status), check with them whether this requires backend/API changes before implementing.
- check knowledge first: workflow.md - Before changing code in documented areas (pools, RemUnits, pool restart, event ordering, conventions), look up the relevant facts with the knowledge skill (kb.py) first.
- code verification: workflow.md - Verify code changes by building, add unit tests for core logic changes, and run the existing tests.
- work items for agent tasks / Colossus work items / gitlab: workflow.md - For any Colossus task the agent works, open one GitLab work item on gitlab.colossusbets.com, in the project for the repo being changed, assigned to the user you are working for.
- debugging / debug no code until confirmed / debug no changes / debug verify: workflow.md - When debugging, verify theories and propose fixes, but don't change code until the user confirms.
- gitlab / gitlab comments: workflow.md - Comments on someone else's GitLab issue still need the user's go-ahead.
- local engine / debugging: workflow.md - DO NOT run the engine locally when working with staging environment.

## Parent
- [../index.md](../index.md)
