---
name: pool-settlement-error
description: >-
  Investigate wrong fantasy pool settlements (FANTASY_OU, Pick'em, commingled pools).
  Diagnose stale metrics, fantasy approval gates, stats_feed vs tote drift, and
  prepare manual correction + internal post-mortem. Use when a pool settled wrong,
  legs show incorrect OVER/UNDER, metric amounts disagree with box score, or ops
  reports settlement errors.
---

# Pool settlement error investigation

## Goal

Find **why** a pool settled with wrong leg results, separate upstream (SportsData) from internal causes (approval gate, pipeline, ops), and deliver correction artifacts + post-mortem.

## Before you start

1. **Confirm environment**: UK production (`user-production_uk_cbtote`), US fantasy commingled (`user-production_us_fantasy_cbtote`), or staging.
2. **Get from reporter**: pool ID, which legs are wrong, expected vs actual metric values, settlement time (UTC).
3. **Look up the Colossus KB** with the `knowledge` skill: `kb.py read current-by-category --path-prefix business/pools`, then `read search` for the metric or flow involved (fantasy approvals, StatsFeed, settlement).
4. **Check cbstatsfeed** code in `cbstatsfeed` repo (submodule or sibling): `FantasyOverUnderMetricsProcessor`, `ToteMetricsService`.

## Investigation checklist

```
- [ ] 1. Pool metadata (type, status, commingled mirror, fixtures)
- [ ] 2. Per-leg settled values (market_results, legs)
- [ ] 3. Flags: manual_override, settle_manually, fantasy_approvals
- [ ] 4. Timeline: stats_feed histories vs FOU_UPD vs OFFICIAL
- [ ] 5. Root cause classification (see decision tree)
- [ ] 6. Cross-check public play-by-play (before blaming SportsData)
- [ ] 7. Impact: winning_selections, payout delta, commingled pools
- [ ] 8. Correction: offer regen + post-mortem
```

---

## Step 1 — Pool and leg snapshot

```sql
-- Pool overview
select id, name, type_code, sport_code, status, settlement_status,
       sched_start, settled_at, commingled_pool_id
from pools where id = :pool_id;

-- Legs with settled metric amounts
select l.leg_order, l.id as leg_id, l.official, sep.name as player,
       m.code as metric,
       json_extract(mr.result, '$.metric_amount') as settled_amount,
       json_extract(mr.result, '$.over_under_threshold') as line,
       json_extract(mr.result, '$.market_result') as market_result
from legs l
join legs_markets lm on lm.leg_id = l.id
join market_results mr on mr.market_id = lm.market_id and mr.sport_event_id = l.sport_event_id
join market_metrics mm on mm.market_id = lm.market_id
join metrics m on m.id = mm.metric_id
join sport_event_players sep on sep.id = mm.sport_event_player_id
where l.pool_id = :pool_id
order by l.leg_order;
```

Note commingled US pool ID and any other live pools on the same fixture:

```sql
select distinct p.id, p.name, p.status
from pools p
join legs l on l.pool_id = p.id
where l.sport_event_id in (
  select sport_event_id from legs where pool_id = :pool_id
);
```

---

## Step 2 — Fantasy approval gate (most common FANTASY_OU cause)

For FANTASY_OU pools, **threshold crossings create `fantasy_approvals` instead of FOU_UPD** until ops approves.

```sql
select fa.id, l.leg_order, sep.name, m.code,
       fa.new_metric_value, fa.approved, fa.approved_by, fa.approved_at, fa.created_at
from fantasy_approvals fa
join market_metrics mm on mm.id = fa.market_metric_id
join metrics m on m.id = mm.metric_id
join sport_event_players sep on sep.id = mm.sport_event_player_id
join legs_markets lm on lm.market_id = mm.market_id
join legs l on l.id = lm.leg_id
where l.pool_id = :pool_id
order by fa.created_at;
```

Also check manual flags:

```sql
select l.leg_order, sep.name, m.code,
       mm.manual_override,
       json_extract(mr.result, '$.settle_manually') as settle_manually
from legs l
join legs_markets lm on lm.leg_id = l.id
join market_metrics mm on mm.market_id = lm.market_id
join market_results mr on mr.market_id = lm.market_id and mr.sport_event_id = l.sport_event_id
join metrics m on m.id = mm.metric_id
join sport_event_players sep on sep.id = mm.sport_event_player_id
where l.pool_id = :pool_id
order by l.leg_order;
```

**Red flags:**
- Pending approval (`approved` null, no `approved_by`) at OFFICIAL time → **approval gate**
- `manual_override = 1` → operator blocked automated updates
- **Low OU line (e.g. 0.5 K)** → first in-game event triggers approval; tote may never show any live value

---

## Step 3 — Three-way timeline

Compare three sources for each wrong leg:

| Source | What it proves |
|--------|----------------|
| `mlb_player_fixture_stats_histories` (stats_feed MCP) | What SportsData delivered per poll (~15s) |
| `sport_event_histories` FOU_UPD (cbtote) | What we published to the pool |
| OFFICIAL row | What we settled on |

**stats_feed** (MLB example — adjust for sport):

```sql
select h.created_at, p.name, h.pitching_strikeouts,
       (coalesce(h.hits,0)+coalesce(h.runs,0)+coalesce(h.runs_batted_in,0)) as hits_runs_rbi
from mlb_player_fixture_stats_histories h
join mlb_players p on p.external_id = h.player_id
where h.global_game_id = :global_game_id and h.player_id = :player_ext_id
order by h.created_at;
```

**cbtote FOU_UPD**:

```sql
select seh.created_at, seh.event_code, jt.metric_code, jt.metric_amount
from sport_event_histories seh
join json_table(seh.event_info_json, '$.market_results[*]' columns (
  player_id int path '$.player_id',
  metric_code varchar(50) path '$.metric_code',
  metric_amount decimal(10,1) path '$.result.metric_amount'
)) jt
join sport_event_players sep on sep.id = jt.player_id
where seh.sport_event_id = :sport_event_id
  and sep.competitor_id in (select competitor_id from sport_event_players where id = :sport_event_player_id)
  and jt.metric_code = :metric_code
  and seh.event_code in ('FOU_UPD', 'COMPLETED', 'OFFICIAL')
order by seh.created_at;
```

**Interpretation:**
- stats_feed correct **during IN_PLAY**, tote stale → **internal** (approval gate, IN_PLAY gate, sparse FOU_UPD)
- stats_feed stale at OFFICIAL → possible upstream lag (verify before escalating)
- Gap in stats_feed matches **inning/plate-appearance spacing** on public play-by-play → **not** SD lag

---

## Step 4 — Root cause decision tree

```
Wrong settlement reported
│
├─ fantasy_approvals pending at OFFICIAL?
│   └─ YES → PRIMARY: approval gate + ops did not action queue
│
├─ manual_override = 1?
│   └─ YES → operator blocked feed updates
│
├─ stats_feed had correct value before OFFICIAL, tote did not?
│   ├─ FANTASY_OU + crossed threshold → approval gate (cbstatsfeed)
│   ├─ fixture left IN_PLAY before final push → ToteMetricsService IN_PLAY-only gate
│   └─ duplicate sport_event_players (one missing ext_id) → player mapping issue
│
├─ stats_feed stale at OFFICIAL?
│   ├─ cross-check ESPN/MLB Gameday play-by-play
│   ├─ gap = real game pacing → NOT upstream lag
│   └─ gap = event occurred long before feed updated → consider SportsData SLA ask
│
└─ tote values correct at OFFICIAL but engine settled wrong?
    └─ engine/settlement logic bug (rare; verify market_results at OFFICIAL first)
```

### Key code paths (cbstatsfeed)

| Component | Behavior |
|-----------|----------|
| `ToteMetricsService.UpdateToteMetrics` | **Only runs when fixture IN_PLAY** and pool IN_PLAY |
| `FantasyOverUnderMetricsProcessor` | Below threshold → auto FOU_UPD; above threshold+buffer → `CreateApproval` |
| `MlbGameHistoriesService.StorePlayerGamesHistory` | Post-game history **does not** push to tote |

Settlement buffer: `threshold × (1 + metrics.settlement_buffer_percentage)` (MLB typically 10%).

---

## Step 5 — Cross-check before blaming SportsData

Use public play-by-play to distinguish **feed lag** from **normal game pacing**:

| Source | Use for |
|--------|---------|
| [MLB Gameday](https://www.mlb.com/gameday) | Official inning-by-inning events |
| [ESPN play-by-play](https://www.espn.com/mlb/playbyplay/) | `gameId` from ESPN box score URL |
| [CBS gametracker](https://www.cbssports.com/mlb/gametracker/) | Pitch-by-pitch for some games |

**Do not escalate to SportsData** when:
- stats_feed had correct finals during IN_PLAY before OFFICIAL
- perceived "delay" matches time between plate appearances or innings on play-by-play
- root cause is unapproved `fantasy_approvals`

---

## Step 6 — Correction workflow

1. **Confirm correct final metric values** (operator + stats_feed + public box score).
2. **Build corrected results string** (one digit per leg: 1=UNDER, 2=OVER for FANTASY_OU).
3. **Regenerate offers on production pod** (if applicable):
   - Pod: `enginelinux` in `production-apps` (UK), context `prd`
   - Offer path: `/files/offer_files/{poolId}/`
   - Generator: `/build/offer_generator_sport/offerGenerator`
4. **Compare payouts**: settled vs corrected → ticket-level discrepancies.
5. **Production fix** (ops): update `market_results`, `sport_event_histories`, pool restart, apply commingled mirror pool.
6. **Deliverables**: corrected CSVs, payout discrepancy report, post-mortem.

Store working files under `tmp/pool-{id}-offgen/`.

---

## Step 7 — Post-mortem

Use [post-mortem-template.md](post-mortem-template.md) for the internal report.

Generate Word doc:

```powershell
pip install python-docx  # if needed
python scripts/generate_postmortem_docx.py `
  --output "tmp/pool-{poolId}-offgen/Pool-{poolId}-Post-Mortem.docx" `
  --data "tmp/pool-{poolId}-offgen/postmortem-data.json"
```

Or fill the template manually from investigation findings.

**Post-mortem must include:**
- Executive summary + root cause (not symptoms)
- Wrong legs table (settled vs correct)
- UTC timeline (stats_feed vs FOU_UPD vs approvals vs OFFICIAL)
- What was ruled out (SportsData, manual_override, engine bug)
- Impact (tickets, payout delta, commingled pools)
- Remediation completed vs pending
- Recommendations (ops + engineering)

---

## Reference case: pool 81410 (July 2026)

Canonical example of **approval gate** failure. See [reference.md](reference.md#case-study-pool-81410).

| Leg | Player | Issue |
|-----|--------|-------|
| 1 | Sánchez STRIKES_PITCHING 0.5 | First K triggered approval; tote stayed **0** |
| 3 | Harper HITS_RUNS_RBI 1.5 | Approval at 23:20 for 2; never approved |
| 6 | Vierling HITS_RUNS_RBI 1.5 | Approval at 22:55 for 2; never approved |

SportsData was timely; public ESPN play-by-play confirmed Harper's 2nd hit was 5th inning (not feed lag).

---

## MCP servers

| Server | Use |
|--------|-----|
| `user-production_uk_cbtote` | UK pools, fantasy_approvals, FOU_UPD |
| `user-production_us_fantasy_cbtote` | US commingled mirror |
| `user-staging_mysql_stats_feed` | `mlb_player_fixture_stats_histories` |
| `user-production_mysql_cbtote` | Production if UK MCP unavailable |

## Agent behavior

- Work through the checklist; do not blame SportsData until three-way timeline + play-by-play cross-check.
- For FANTASY_OU, **always query `fantasy_approvals`** early.
- Distinguish settlement-direction errors (UNDER vs OVER) from wrong metric amount with same outcome.
- Produce post-mortem for any production settlement error affecting payouts.
- Do not apply production fixes without explicit user approval.

## Additional resources

- SQL queries and ID lookups: [reference.md](reference.md)
- Post-mortem markdown template: [post-mortem-template.md](post-mortem-template.md)
- DOCX generator: [scripts/generate_postmortem_docx.py](scripts/generate_postmortem_docx.py)
