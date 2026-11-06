# Pool settlement error — reference

## Table map

| Table | Purpose |
|-------|---------|
| `pools` | Pool status, type, commingled_pool_id |
| `legs` | leg_order, sport_event_id, official flag |
| `legs_markets` | leg → market |
| `market_results` | JSON result: metric_amount, over_under_threshold, market_result |
| `market_metrics` | manual_override, sport_event_player_id |
| `fantasy_approvals` | Pending/approved OU threshold crossings |
| `sport_event_histories` | FOU_UPD, COMPLETED, OFFICIAL events |
| `sport_event_players` | Player on fixture; link via competitor.ext_id |
| `mlb_player_fixture_stats_histories` | stats_feed poll history (SportsData proxy) |

## fantasy_approvals schema

| Column | Notes |
|--------|-------|
| `market_metric_id` | FK to market_metrics |
| `new_metric_value` | Proposed value (may be stale if feed moved on) |
| `approved` | null = pending |
| `approved_by` | null = pending; empty check used in code |
| `created_at` | When threshold first crossed |

## Player ext_id lookup

```sql
select sep.id, sep.name, sep.competitor_id, c.ext_id, sec.sport_event_id
from sport_event_players sep
join sport_event_competitors sec on sec.id = sep.sport_event_competitor_id
left join competitors c on c.id = sep.competitor_id
where sec.sport_event_id = :sport_event_id
  and sep.name like :name_pattern;
```

Watch for **duplicate rows** (same name, one without ext_id). Pool leg uses `market_metrics.sport_event_player_id` — verify it has `competitors.ext_id` set.

## Fixture → SportsData game ID

```sql
select se.id, se.external_id, se.name, se.status
from sport_events se
join legs l on l.sport_event_id = se.id
where l.pool_id = :pool_id;
```

Map `external_id` to stats_feed `global_game_id` for MLB.

## Settlement buffer

```sql
select code, settlement_buffer_percentage
from metrics
where code in ('STRIKES_PITCHING', 'HITS_RUNS_RBI', 'WALKS_ALLOWED', 'RUNS');
```

Approval threshold = `over_under_threshold * (1 + settlement_buffer_percentage)`.

## FOU_UPD batch behavior

FOU_UPD events often include **all** market_results on a fixture, not just the changed player. A player showing 0 in every FOU_UPD does not mean the processor ran for that player — check whether metric_amount ever changed.

## Offer regeneration (production UK)

| Item | Value |
|------|-------|
| Namespace | `production-apps` |
| Pod label | `app=enginelinux` |
| Context | `prd` (aws-production-uk) |
| Offer files | `/files/offer_files/{poolId}/` |
| Generator binary | `/build/offer_generator_sport/offerGenerator` |

Workflow:
1. Pull latest settlement inputs from current offGenId on pod.
2. Create corrected `Results`, `Probabilities`, `Offers`, `Payouts` with new offGenId.
3. Run offer generator; capture payout discrepancy vs settled.

## Log investigation (optional)

cbstatsfeed logs around approval creation:

```
app=~"cbstats-feed-daemon-mlb"
|~ "Creating approval for player"
|~ "{player_ext_id}|{metric_code}"
```

Use `grafana-loki-logs` skill for logcli workflow.

## Public cross-check URLs

| Game | ESPN play-by-play |
|------|-------------------|
| PHI @ DET 2026-07-11 | `gameId/401816117` |
| ARI @ LAD 2026-07-11 | `gameId/401816108` |

MLB Gameday: `https://www.mlb.com/gameday/{game_pk}` (e.g. 824249 for PHI@DET 2026-07-11).

## Case study: pool 81410

| Field | Value |
|-------|-------|
| UK pool | 81410 |
| US commingled | 1659 |
| Type | FANTASY_OU Pick'em 10 |
| Fixture Tigers | 428336 / SportsData 10078716 |
| Fixture Dodgers | 428342 / SportsData 10078714 |
| Wrong results | `1/1/1/1/1/1/2/1/2/2` |
| Correct results | `2/1/2/1/1/2/2/1/2/2` |
| Impact | 67 tickets, +£177.53 net to players |
| offGenId corrected | 304903 |
| Root cause | 3 unapproved fantasy_approvals (#3389, #3390, #3391) |
| Ruled out | SportsData lag, manual_override, engine bug |

### Approval timeline

| ID | Leg | Created (UTC) | Value | Approved |
|----|-----|---------------|-------|----------|
| 3389 | 1 Sánchez | 22:26:45 | 1 | No |
| 3390 | 6 Vierling | 22:55:15 | 2 | No |
| 3391 | 3 Harper | 23:20:01 | 2 | No |
| 3392 | 9 Yamamoto | 01:57:43 | 2 | Yes 04:08 |
| 3393 | 10 Pages | 03:01:44 | 1 | Yes 04:03 |

### Control leg: Mize STRIKES_PITCHING

Line 5.5, final 5 — all values below threshold, FOU_UPDs auto-published 0→1→2→3→4→5. Confirms pipeline works without approval gate.

### Engineering recommendations (from 81410)

1. Block/warn OFFICIAL when pending fantasy_approvals exist.
2. Approval UI: show latest stats_feed value, not stale `new_metric_value`.
3. Post-game final sync when fixture leaves IN_PLAY.
4. Review auto-publish for very low OU lines (0.5 pitcher K).
5. Monitor stats_feed vs tote drift during IN_PLAY.
