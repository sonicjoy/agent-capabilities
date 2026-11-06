<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Conventions Knowledge Index

Coding conventions and quality principles.

**Last Updated**: 2026-03-05

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [code-quality.md](code-quality.md) | Delete over add | 2026-02-04 | - | Removing unnecessary code is more productive than writing new code. |
| [data-fixes.md](data-fixes.md) | Fix duplicated data with SQL scripts | 2026-03-05 | - | Fix duplicate data at the source with SQL scripts, not only defensive code. |

## Quick Reference
- delete over add / refactoring / code quality: code-quality.md - Prefer removing redundant code over adding new code to fix or clarify behavior.
- duplicate data: data-fixes.md - When duplicated data causes runtime errors (e.g. .Single() throwing), fix the data at source using SQL scripts rather than only making the application tolerant (e.g. .First() or "use first and log").

## Parent
- [../index.md](../index.md)
