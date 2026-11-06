<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Debug sequence: MVP market_metrics never updated (created_at == updated_at)

**Added**: 2026-01-27
**Context**: Pool 51177, markets 18432–18435 (GOALS_ASSISTS, CARDS, GOALKEEPER_SAVES, PASSES_COMPLETED). `market_metrics.metric_value` all 0; `created_at == updated_at` (rows never updated). stats_feed–backed API shows correct values for some players; cbtote does not.
**Id**: `mvp-market-metrics-never-updated-2026-01`

> MVP market_metrics stay at their inserted values because the update path (SetResults) is never called, not because 0 is written.

## Summary

- **Observation 1**: stats_feed metric values (e.g. from `soccer_player_fixture_stats`) **also start from null** — so a “fallback to stats_feed” does not fix the source of zeros.
- **Observation 2**: `market_metrics` are **never updated** (`created_at == updated_at`) — the bug is that the **update path is never exercised**, not that we write 0.

## Relevant code (CbStatsDaemon / cbstatsfeed)

| Component | Role |
|-----------|------|
| `SoccerPlayerFixtureStatsProcessor` | Maps `PlayerGame[]` → snapshots; upserts stats_feed; calls `UpdateTotePlayerMetrics` with `getMetricValue(snap, metricCode)`. |
| `GenericTotePlayerFixtureStatsService` | Builds `byPlayer` from snapshots (key = `snap.PlayerId` = SportsData PlayerId). `feedPlayerMetrics(playerId, metricCode)` = `getMetricValue(byPlayer[playerId], metricCode)`; **throws** `KeyNotFoundException` if `playerId` not in `byPlayer`. |
| `ToteMetricsService.UpdateToteMetrics` | Finds pools (InPlay + fantasy), loops legs → markets → `market_metrics`. For each: `metricValue = feedPlayerMetrics(Convert.ToInt32(Competitor.ExtId), metricCode)`. **Catches** exception → logs “player not in the game” → **continues** (skips that `market_metric`). Then `processor.ProcessMetric(market, marketMetric, metricValue, ...)`. |
| `FantasyMvpMetricsProcessor.ProcessMetric` | `currentMetricValue = marketMetric.MetricValue`; `if (currentMetricValue == metricValue) return;` (no `SetResults`). Else `mvpMarketResultService.SetResults(market.Id, results)`. |
| `IMvpMarketResultService.SetResults` | In **CbToteLogic** (NuGet). Whether it updates `market_metrics.metric_value` / `market_metrics.updated_at` is unknown from this repo. |

## Why SetResults is never called (and thus market_metrics never updated)

### Path A: `feedPlayerMetrics` throws → we never call `ProcessMetric`

- `byPlayer` only contains players in the **current** `PlayerGame[]` (from the live delta or batch).
- `feedPlayerMetrics` is called with `playerExtId` = `marketMetric.SportEventPlayer.Competitor.ExtId` (SportsData PlayerId when source is SportsData).
- If that player is **not** in `byPlayer` (e.g. delta returns a subset, or tote market has players not in this game’s `PlayerGame[]`), `byPlayer.TryGetValue(playerId, out var s)` fails → **`KeyNotFoundException`**.
- `ToteMetricsService` catches, logs *"There is a chance the pool was setup with a player not in the game"*, **continues** → `ProcessMetric` is **never** called for that `market_metric` → **SetResults never called**.

### Path B: `ProcessMetric` is called but returns before `SetResults`

- `currentMetricValue` = `marketMetric.MetricValue` (from DB at load, often 0 at insert).
- `metricValue` = `getMetricValue(snap, metricCode)` = `SoccerMetricValueExtractor.GetMetricValue(metricCode, snap)`. With nulls in the snapshot (delta often omits Goals, Assists, PassesCompleted, GoalkeeperSaves, Cards), this is **0**.
- So often **`currentMetricValue == metricValue` (0 == 0)** → `if (currentMetricValue == metricValue) return;` → **SetResults never called**.

## Data flow (simplified)

1. **Live**: `GetBoxScoresDeltaByDate` → `PlayerGame[]` (often null for GOALS_ASSISTS, CARDS, GOALKEEPER_SAVES, PASSES_COMPLETED) → snapshot → `GetMetricValue` → 0.
2. **Batch**: `GetBoxScore` (full) has full stats, but batch only runs when `PlayerStats.Count == 0` and 4h+ old; live usually populates first, so batch often does not run for that game.
3. **stats_feed**: Same `PlayerGame[]` → mapper → upsert. If the API sends nulls, stats_feed also gets nulls; it does not “start ahead” with correct values.

## What to verify (before changing code)

1. **CbToteLogic**
   Does `IMvpMarketResultService.SetResults` (or the code it calls) **UPDATE** `market_metrics` (`metric_value`, `updated_at`)? Or does it only write to `market_results` / `market_histories`, with `market_metrics` updated by triggers/jobs/settlement?

2. **Logs** for the fixture (e.g. `global_game_id` 90091219) and pool 51177:
   - *"There is a chance the pool was setup with a player not in the game"* → Path A (throw → skip `ProcessMetric`).
   - *"Metric value didn't change for {Metric} player {PlayerId}"* → Path B (early return, no `SetResults`).

3. **`market_results`** for markets 18432–18435: any payload at all? If `SetResults` only writes there and it’s empty, that fits with `SetResults` never being called.

## Reverted / not applied

- **Stats_feed fallback** in `SoccerPlayerFixtureStatsProcessor`: reverted. stats_feed also starts from null, so it doesn’t fix the 0 source; and the main finding is that **updates never run** (SetResults not called), not that we deliberately write 0.

## Related

- `technical/architecture/statsfeed-daemon.md` — ToteMetricsService conditions, ID mapping, when tote updates run.
- `technical/workflow/workflow.md` — **Debug: No code changes until user confirms**.
- `technical/cbtote/mvp-uses-market-metrics.md` — **MVP uses market_metrics, NOT market_results**; any MVP flow must update `market_metrics`.
