<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Filtering data: confirm backend support

**Added**: 2026-02-04
**Context**: Fixture selector filtering by external source (e.g. SportsData); API (CbToteLogic FixtureFilter) did not support the parameter, leading to client-side-only filtering and wrong totals.
**Id**: `filtering-data-confirm-backend-support`

When the user asks to filter data (e.g. by source, date range, status), **check with them whether this requires backend/API changes** before implementing. Do not assume the existing API supports the filter; confirm and, if not supported, either implement client-side filtering with clear limitations or agree on adding backend support.
