<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# StatsFeedDaemon – stats and cbtote updates

**Added**: 2026-01-27
**Updated**: 2026-01-27
**Context**: Clarifying how player/event stats reach cbtote; relevant to MVP fantasy metric values and missing metrics (e.g. sport event 400791). Includes original ToteMetricsService conditions (pool InPlay, leg’s event InPlay) and the 2026-01-27 relaxation for finished events and MVP.
**Id**: `statsfeeddaemon-stats-and-cbtote-updates`

> StatsFeedDaemon downloads SportsData stats into stats_feed and writes metrics to cbtote only for markets used in pools.

## Overview

**StatsFeedDaemon** is a separate process that:

1. **Downloads stats** from the **SportsData API**
2. **Writes** those stats into the **stats_feed** database
3. **Updates cbtote** by writing **market_metrics** (or equivalent metric data) **only for markets that are used in pools**

## ID mapping: cbtote ↔ stats_feed

For **`sport_events`** where **`external_source_code = 'SportsData'`**:

- **`sport_events.external_id`** = **`global_game_id`** in the **stats_feed** database.

Use this to join or correlate cbtote sport events with stats_feed when the source is SportsData.

## Relation to cbtote schema

- In cbtote, the **`market_metrics`** table links markets to metrics and `sport_event_players` (which players and metric types are in each market). It does **not** store the numeric stat values.
- The **metric values** used for MVP fantasy settlement are in **`market_histories.market_snapshot`** (e.g. `metric_value` per `market_metric_id` / player).
- If StatsFeedDaemon “updates market_metrics” in the broad sense of “metrics on markets used in pools”, it may write to `market_histories.market_snapshot` (and/or to another table that feeds it). The exact tables and flow should be confirmed in the StatsFeedDaemon codebase.

## ToteMetricsService: when tote updates run (original logic)

**CbStatsDaemon** (ToteMetricsService) only ran tote updates when **both** of these were true:

1. **Pool status = InPlay**
   `ToteMetricsService` filtered with `p.Status == Constants.PoolStatus.InPlay`. Pools that were Settling, Settled, or Closed were excluded.

2. **Leg’s sport event = InPlay**
   If `leg.SportEvent` was not InPlay (e.g. COMPLETED, OFFICIAL), that leg was skipped and no metrics were written for it.

**Why it matters:**
For sports like soccer, final player stats often arrive only after the match (e.g. 4+ hours via SoccerPlayerFixtureStatsExtractor). By then the event is COMPLETED/OFFICIAL and the pool is often no longer InPlay, so no pools (and/or legs) passed these checks and `market_metrics` / `market_histories.market_snapshot` were never updated. This caused missing metric values for MVP fantasy (e.g. sport event 400791).

**As of 2026-01-27:** The logic was relaxed so that:
- Pools are also included when the **sport event** is COMPLETED, OFFICIAL, or Abandoned (not only when the pool is InPlay).
- For **FantasyMvp** legs, the “leg’s sport event must be InPlay” check is not applied, so final metrics can be pushed for finished matches.

## Implication for missing metrics

When `market_histories.market_snapshot` has all `metric_value` = 0 for an event (e.g. sport event 400791), possible causes include:

- StatsFeedDaemon did not receive or could not map stats from SportsData for that event
- StatsFeedDaemon did not run or failed for that event
- The event’s markets were not treated as “used in pools” (e.g. filtering or timing)
- **Historically:** The original ToteMetricsService conditions (pool InPlay + leg’s event InPlay) excluded finished events and MVP when stats arrived post-match — see “ToteMetricsService: when tote updates run” above.
- A bug or misconfiguration in how StatsFeedDaemon maps SportsData → `market_histories.market_snapshot` (or the path that feeds it)
