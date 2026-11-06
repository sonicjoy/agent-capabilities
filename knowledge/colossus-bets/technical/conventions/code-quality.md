<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Deleting Unnecessary Code Is More Productive Than Writing New

**Added**: 2026-02-04
**Context**: Refactoring RemUnitsController (enginelinux)—removed LegCompleted and used only LegOfficial
**Id**: `delete-over-add`

Prefer removing redundant code over adding new code to fix or clarify behavior. Deleting unnecessary state, duplicate logic, or unused paths reduces surface area, simplifies reasoning, and often fixes bugs (e.g. one source of truth instead of two that can drift).

**Examples**: Removing the LegCompleted flag entirely and using LegOfficial for all “leg is settled” logic instead of adding another flag or more comments.
