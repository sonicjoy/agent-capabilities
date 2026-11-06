<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# RemUnitsController and SEP behaviour

MarketHistories, LegOfficial, remaining-unit skip rules, strategy split (is_match_kind).

---

## Do not reload pool on each message (TicketList)
**Added**: 2026-02-11
**Context**: Pool 51282 — ticket distribution had 0 units on all selections. Logs showed `UpdateRemainingUnits()--> FOR 0 remaining Tickets` even though the DB had 1 valid live ticket.
**Id**: `no-pool-reload-per-message`

> Don't reload the pool from the DB on each sport event history message: GetPoolAsync doesn't load TicketList, so units stay 0; use the pool given at start.

**Cause**: `ProcessSpEvHistMsg()` was reloading the pool with `GetPoolAsync()` on every sport event history message. `GetPoolAsync()` does not load `TicketList` (tickets are loaded only at pool start in `ToteController.StartPoolAsync`, or on explicit reload_tickets). The new pool had default `TicketList = []`, so `LiveSet` was empty and all ticket distribution units stayed 0.

**Rule**: **Do not reload the pool from DB on each message.** The controller uses the pool (and its `TicketList`) provided at Start. Remaining-unit state is event-sourced from the message stream; LegOfficial, WinBins, etc. are updated from events, not by re-reading the pool. Reloading on every message was unnecessary and caused TicketList to be lost.

**Implementation**: `RemUnitsController.ProcessSpEvHistMsg()` — no `GetPoolAsync` / `SetPool`; use `_ruCtrlContext.Pool` as-is.

---

## Flow strategy (pool-type-agnostic controller)
**Added**: 2026-02-09
**Id**: `rem-units-flow-strategy`

RemUnitsController no longer branches on `IsMatchPool` for processing. It uses **IPoolEventFlowStrategyFactory** to get the strategy for the pool (**MarketBasedPoolEventFlowStrategy** for match/SEP pools, **SportEventBasedPoolEventFlowStrategy** for sport-event-based (e.g. racing)). The strategy returns a **SportEventProcessResult** (Refresh, ResetTickets, per-leg updates: WinBins, Official, FavouriteBins, WithdrawnBins; SEP amendment adds ResetRuOfficial). The controller applies the result to `_poolContext`, runs any ResetRuOfficial DB updates for SEP, then calls UpdateRemainingUnits, UpdateTickets, PublishPoolUpdateMsg. Market status and LegOfficial rules are unchanged (market status from event's MarketHistories; LegOfficial in-memory only).

---

## LegOfficial vs DB leg.official for Shutdown
**Added**: 2026-02-06
**Updated**: 2026-02-10
**Id**: `leg-official-for-shutdown`

RemUnitsController shutdown is based only on **in-memory `_ruCtrlContext.LegOfficial`** (set when we process OFFICIAL/ABANDONED and set `settled = true`). Do not use DB `leg.official` for exit. If we never set LegOfficial during event processing (e.g. always hit Completed branch), the controller can stay in play even when DB says all legs official.

**No DB sync**: We do not reload the pool after each message or sync LegOfficial from DB. Recovery for stuck pools is via **pool restart**; no fallback sync in the main loop.

**Implementation**: `RemUnitsController.RuCtrlThread()` — exit check uses `AreAllLegsOfficial()` which reads `_ruCtrlContext.LegOfficial` only.

---

## Pool event flow strategy split (match vs non-match)
**Added**: 2026-02-11
**Context**: Correct understanding of which pools use MarketBased vs SportEventBased; unit test coverage.
**Id**: `pool-flow-strategy-split`

> Match pools (type_code with is_match_kind = 1) use MarketBasedPoolEventFlowStrategy; all other pools use SportEventBasedPoolEventFlowStrategy.

**Definition**

- **IsMatchPool** = `CommonHelpers.MatchTypeCodes.Contains(pool.type_code)` (`PoolObj.IsMatchPool`).
- **MatchTypeCodes** = type_codes where **`type_code_descriptions.is_match_kind = 1`**, loaded at startup via **`DataAccessLayer.GetMatchTypeCodesAsync()`** (used by `ToteController.StartAsync` and by test `ServiceProviderFixture`).

**Split**

- **Match pools** (`is_match_kind = 1`) → **MarketBasedPoolEventFlowStrategy** (market/SEP path; legs per market; status from MarketHistories).
- **All other type_codes** (`is_match_kind = 0` or not in list) → **SportEventBasedPoolEventFlowStrategy** (sport-event/racing path; leg per event; competitors, COMPLETED only for HORSE_RACING/GREYHOUNDS).

**Test seeds (new_tote_seeds.sql)**
`is_match_kind = 1` only for: **AVB, FANTASY_OU, FANTASY_MARGIN, MATCH**. (FANTASY_MVP is added with `is_match_kind = 1` when fantasy_mvp_pool seed runs.) So CORRECT_SCORE, BTTS, HDA, RACE_WIN, RACE_PLACE, RACE_ORDER, etc. are **non-match** and use SportEventBased.

**Implementation**

- `PoolEventFlowStrategyFactory.GetStrategy(pool)` → `pool.IsMatchPool ? marketBasedStrategy : sportEventBasedStrategy`.
- `RemUnitsController` uses the strategy for processing; no branch on IsMatchPool for which strategy to use.

**Unit tests**

- **SportEventBasedPoolEventFlowStrategyTests**: Non-match path. TheoryData currently only covers **racing** (RACE_WIN, RACE_PLACE, RACE_ORDER × GREYHOUNDS, HORSE_RACING, WRC) because those need minimal context; other non-match types (e.g. FOOTBALL CORRECT_SCORE, BTTS) would need market histories / event_info_json to return LegUpdates and are not yet in TheoryData.
- **MarketBasedPoolEventFlowStrategyTests**: Match path. Single fact that factory returns `MarketBasedPoolEventFlowStrategy` for pool 50019 (FANTASY_OU). Full (event, type, sport) coverage with LegUpdates is in **FantasyToteControllerTests** (RunFantasyOuPoolToCompletion, RunFantasyMarginPool, RunFantasyMvpPool_*).
- **ServiceProviderFixture** sets `CommonHelpers.MatchTypeCodes = dal.GetMatchTypeCodesAsync().Result` so test DB `type_code_descriptions.is_match_kind` drives IsMatchPool in tests.

---

## Premature Exit: Replay vs DB and Vacuous Truth
**Added**: 2026-02-09
**Context**: Pool 51347 — log showed "Legs official status: 1:False,2:False,3:False" then "All events official and queue is empty, exiting loop". DB confirmed all three legs had `official = 0`; pool had just started.
**Id**: `premature-exit-vacuous-truth`

> The controller exited early because replay marked legs official in memory (LegOfficial) while the DB still had them unofficial, not because a pool had no legs.

**Likely cause (replay)**: Pools cannot go IN_PLAY without legs, so "pool passed with no legs" is very unlikely. The plausible cause is **replay**. In `ProcessPreviousExistingHistory()` we replay sport event histories and set `LegOfficial[leg] = true` in context when we process OFFICIAL/ABANDONED. We do **not** update DB during replay (`SetLegOfficialAsync` is called by ToteController when processing live). So after replay we can have **context all true** while **DB has legs unofficial** (e.g. pool restarted and legs reset, or engine restarted). When we then enter the message loop, `AreAllLegsOfficial()` is true (context only) → we exit.

**Proper event-sourcing (replay)**: Do **not** sync context from DB after replay (that would overwrite context with DB state and can skip events that arrived during replay). Instead: after replay, load any sport event histories with **id > max(replayed id)** via `GetSpEventHistoriesForPoolAfterIdAsync(poolId, maxReplayedId)` and **process them in order** (same path as replay: ProcessSepHistory/ProcessSportEventHistory, UpdateRemainingUnits). Then context is always derived from processing events in order; no events skipped, no DB overwrite.

**Defence (vacuous truth)**: `AreAllEventsOfficial()` was also vulnerable when `LegOfficial` is **empty**: `.Values.All(l => l)` is vacuously true. Require `_poolContext.LegOfficial != null && _poolContext.LegOfficial.Count > 0` so we never exit with no legs in context. Keep event-sourcing: use LegOfficial only, no DB in the predicate.

---

## RU History Skip Rules in One Place
**Added**: 2026-02-06
**Id**: `ru-history-skip-rules-in-one-place`

> All rules for skipping a remaining-unit history row live in one method, ShouldSkipRemUnitHistoryRow; amendments are never skipped.

All "skip this remaining unit history row" rules live in **one method** (`ShouldSkipRemUnitHistoryRow`): MVP+COMPLETED (do not add RU history), distribution-only events (withdrawal/favourite/reinstate), prize already at 0 with OFFICIAL/ABANDONED. Amendments are never skipped. This avoids duplicate or scattered skip logic.

**Implementation**: `RemUnitsController.UpdateRemUnitHist()` calls `ShouldSkipRemUnitHistoryRow()` per row.

---

## Sport event history snapshot (event_info_json / add_info)
**Added**: 2026-02-10
**Id**: `seh-snapshot-event-info`

Sport event histories carry snapshot data (e.g. **event_info_json**; any **add_info_json**-style snapshot if present) that **SHOULD** supply what remaining-unit controller logic needs. This snapshot is **managed and updated by Console** (internal admin system).

**Reality**: Due to continuous development we are **not guaranteed** to have all required data in the snapshot (e.g. older histories written before new fields existed, or new features that need data not yet in the snapshot). So:

- **Prefer** history snapshot when present and sufficient (replay-safe; correct as-of that event).
- **Fall back** to current sport event from DB when the snapshot is missing or incomplete — with the caveat that on replay, “current” state (status, scores, add_info_json, competitors) may differ from the state at that history and can be wrong.

When adding new RU logic that needs data from the event, consider whether it can be supplied from the history snapshot (and, if so, whether Console already persists it or needs to be extended). Document any fallback to current sport event so replay behaviour is understood.

---

## Use Market Status from Event's MarketHistories (SEP)
**Added**: 2026-02-06
**Context**: Pool 51329 / market 18607 — leg not going official when market status was Official.
**Id**: `sep-market-status-from-markethistories`

For SEP (match) pools, when deciding Completed vs Official vs ShouldSettle, use **market status from the current event's `MarketHistories`** (match `market_id` to `leg.Market.Id`), not only `leg.Market.Status`. The leg's market object may not be updated per event; the event payload has the correct status for that history row.

Fallback to `leg.Market.Status` when the event has no matching MarketHistory.

**Implementation**: `WinningBinCalculator.CalculateWinningBins()` (SEP branch) — `marketStatus = marketHistory?.market_status ?? leg.Market.Status`.
