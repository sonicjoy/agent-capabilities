<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Pool Business Rules

Tote pool rules: pool categories (leg-per-event, SEP, Fantasy, MVP), withdrawals, favourites, unit allocation, event ordering, pool restarts.

---

## Abandoned Future Leg Remaining Units
**Added**: 2026-01-26
**Id**: `abandoned-future-leg-remaining-units`

Abandoning a future leg (a leg that hasn't started) does not change remaining units. Only legs that have started or are in progress affect remaining units when abandoned. This prevents premature elimination of tickets for legs that haven't begun.

**Implementation**: `SepEventsManager.ProcessAbandoned()`, `RemUnitsController.ProcessSportEventHistory()`

---

## MVP: Remaining Units When All Sport Events Terminal (Issue #151)
**Added**: 2026-02-06
**Context**: Units on lost selections before market official; align with horse racing behaviour.
**Id**: `mvp-remaining-units-all-events-terminal`

Remaining units and ticket distributions must be updated when **all sport events of a leg** are in a terminal state (Completed, Official, or Abandoned). At that point, "lost" selections (e.g. MVP players whose final metric is lower than the max) have their units removed in the calculation.

**For MVP specifically**:
- On **COMPLETED** (market completed, not yet official): recalculate winning bins (so lost players are excluded), update ticket distributions, and update in-memory state—but **do not** add rows to `remaining_unit_histories`. So the FE does not show an extra "COMPLETED" RU history step.
- On **OFFICIAL** (or when market status is Official / all players official): add remaining unit history rows and set the leg as official so the pool can complete.
- Only the OFFICIAL step (or equivalent) writes to `remaining_unit_histories` for MVP; COMPLETED updates state only.

**Settled flag**: `settled = true` means "market has a final result at this event". It drives whether we persist winning selections (DB) and set `LegOfficial` (in-memory). COMPLETED must not set `settled = true`; only OFFICIAL (or market Official / ShouldSettle) sets it so the pool can complete.

**Implementation**: `WinningBinCalculator` (SEP: Completed vs ShouldSettle), `RemUnitsController.UpdateRemUnitHist` (ShouldSkipRemUnitHistoryRow: MVP+COMPLETED skip), `SepEventsManager` (OFFICIAL → ProcessScoreUpdate).

---

## OFFICIAL Event Must Affect Leg (Match Pools)
**Added**: 2026-02-06
**Id**: `official-event-affects-leg`

For match/SEP pools, an **OFFICIAL** sport event history must always be processed as a score/settlement update for the affected leg. It must not be discarded based on DB mapping (`sport_event_histories_codes_market_types`). Otherwise the leg never gets `LegOfficial` set and the pool stays in play.

**Implementation**: `SepEventsManager.ProcessEventCode` — OFFICIAL is an explicit case that routes to `ProcessScoreUpdate`, not to `DiscardUpdate`.

---

## Pool Categories (Domain Context)
**Added**: 2026-02-09
**Context**: Refactoring plan; clarify that the split is not simply "SEP vs racing".
**Id**: `pool-categories-domain-context`

There are two main **pool categories**; the split is **not** "SEP vs racing".

1. **Leg-per-event pools (original model)**
   - **1 leg : 1 sport event.**
   - **Racing**: One leg per race; winners decided by **finishing positions** (places).
   - **Match/football (and similar)**: One leg per match; winners decided by **match result** (e.g. HDA, correct score, BTTS).

2. **Single Event Pools (SEP)**
   - **Multiple legs : 1 sport event.** Introduced after leg-per-event pools.
   - Winners are **not** decided by the sport event score (or horse places) but by **specific metrics** from that same sport event (e.g. player goals, player passes, fantasy points).
   - Examples: markets on metrics from one event (e.g. corners, goals). Fantasy and MVP extend this (see SEP, Fantasy, and MVP evolution below).

**In code**: `IsMatchPool` (from `CommonHelpers.MatchTypeCodes`) selects the processing path. Pools whose `type_code` is in that list use the SepEventsManager path (multiple legs per event, market status from MarketHistories); others use the leg-per-event path (e.g. racing). Use domain terms **leg-per-event** vs **SEP** (and within leg-per-event: racing vs match result) in naming and docs so SEP clearly means "multiple legs, metrics-based", not "all non-racing".

---

## Pool Restart on Abandoned Unstarted Leg
**Added**: 2026-01-26
**Id**: `pool-restart-on-abandoned-unstarted-leg`

Abandoning a sport event in an unstarted leg should NOT restart the pool. Pool restarts should only occur when abandoning legs that have already started. Pool restarts are expensive operations that reprocess all existing sport event histories.

**Implementation**: `ToteController.ProcessSpEvHistory()`, `WinningSelectionsService.SetWinningSelections()`

---

## Pool Restart Sport Event History Ordering
**Added**: 2026-01-26
**Id**: `pool-restart-event-ordering`

When restarting a pool, sport event histories must be processed in chronological order (by `SEH.id ASC` or `SEH.created_at ASC`). Processing in reverse order causes incorrect remaining unit calculations.

**Implementation**: `DataAccessLayer.GetSpEventHistoriesForPoolAsync()` must order by `SEH.created_at ASC`

---

## SEP, Markets, Fantasy, and MVP (Evolution)
**Added**: 2026-02-09
**Context**: Domain evolution from SEP to Fantasy to MVP.
**Id**: `sep-markets-fantasy-and-mvp-evolution`

> SEP pools link legs to metrics through markets rather than event results; Fantasy extends SEP with player metrics across events, and MVP extends Fantasy.

- **SEP (Single Event Pools)**: We introduced the concept of **markets** for SEP to link **metrics in market results to legs**, rather than using event results directly. Multiple legs on one sport event; each leg corresponds to a market whose result is driven by metrics.

- **Fantasy pools**: Extend SEP by betting on metrics from **more than one sport event** (not just one). They focus on **player metrics** (e.g. goals, passes), rather than things like Corners that are typical in SEP.

- **MVP**: Extends Fantasy further. In MVP, **one leg is not limited to players from a single sport event**; a leg can include players from **multiple sport events**. So the same leg can aggregate player metrics across several fixtures.

---

## STARTED Event Chronological Order
**Added**: 2026-01-26
**Id**: `started-event-chronological-order`

STARTED events must be the first events chronologically. When ordering sport event histories, STARTED events appear before COMPLETED, OFFICIAL, ABANDONED, or any other event codes. The STARTED event is processed once per pool (when the first event starts).

**Implementation**: `RemUnitsController.ProcessSportEventHistory()`, `SepEventsManager.ProcessStarted()`

---

## Withdrawn Player/Runner Unit Re-allocation
**Added**: 2026-01-23
**Updated**: 2026-01-28
**Id**: `withdrawn-unit-reallocation`

When a player or runner is withdrawn from a pool leg, their units must be moved to the favourite player/runner for that leg.

**Key points**:
- Applies to all pool types that support withdrawals (horse racing, MVP pools)
- Re-allocation happens regardless of whether the leg is official or still in-play
- For MVP pools: favourite identified via `pool_favourite` in market snapshot
- For racing pools: favourite identified via `sport_event_competitors` with `favourite = true`

**Edge case**: Withdrawals can occur before favourite is set. When favourite is set later (via `UPDATE_FAVOURITE` event), the next recalculation must redirect previously withdrawn units. System uses state-based logic from latest market_snapshot, not historical event order.

**Implementation**: `TicketMini.GetValidSelections()`, `RemUnitsController.SetFavouriteAndWithdrawnBins()`, `RemUnitService.CalculateRemainingUnits()`
