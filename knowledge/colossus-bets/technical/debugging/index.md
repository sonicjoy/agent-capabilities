<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Debugging Knowledge Index

Debug methods and recorded investigations.

**Last Updated**: 2026-01-28

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [database-first-debugging.md](database-first-debugging.md) | Database-first debugging | 2026-01-28 | - | Start with database investigation before code analysis. |
| [mvp-market-metrics-2026-01.md](mvp-market-metrics-2026-01.md) | MVP market_metrics never updated (2026-01) | 2026-01-27 | - | created_at == updated_at; SetResults never called; the two failure paths. |

## Quick Reference
- Debugging methodology: database-first-debugging.md - Always start debugging with database investigation before making code changes or assumptions.
- market_metrics / SetResults / stats_feed fallback / MVP market_metrics: mvp-market-metrics-2026-01.md - MVP market_metrics stay at their inserted values because the update path (SetResults) is never called, not because 0 is written.

## Parent
- [../index.md](../index.md)
