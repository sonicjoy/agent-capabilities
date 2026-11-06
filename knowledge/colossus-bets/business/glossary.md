<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Glossary

Domain terms for PMs and engineers (SEP, MVP, RU, commingling host/guest, leg official, ...).

---

## BB (player props)
**Added**: 2026-10-09
**Id**: `glossary-bb`

> The player-props product: customers build entries on player statistics; it has its own back end (bb-tote).

**BB** is the player-props contest product (bet builder). Its back end is `bb-tote` with its own database (`bb_tote`, entries instead of tickets); it reads cbtote and takes player data from the stats feed. Live BB entries belong to the Fantasy merchant (255).

---

## Commingling (host and guest)
**Added**: 2026-10-09
**Id**: `glossary-commingling`

> Sharing one pool across several totes so their customers bet into the same pot; the tote that owns the pool is the host, the others are guests.

**Commingling** lets several totes (gateways) offer the same pool with one shared pot. The **host** is the tote where the pool and its actions originate; **guests** are the other totes, which receive copies of the pool, results and settlements and send their tickets back. ComminglingFeedSystem (CFS) does the replication through Kafka and S3.

---

## Completed vs official
**Added**: 2026-10-09
**Id**: `glossary-completed-vs-official`

> Completed means the event has finished; official means the result is final and can be paid out.

**Completed:** the event (or market) has finished, but the result can still change. **Official:** the result is confirmed (e.g. "weighed in" in racing) and settles the leg. For MVP, COMPLETED only updates state; only OFFICIAL writes RU history and lets the pool complete.

---

## Cycle data and cycledata_finalised
**Added**: 2026-10-09
**Id**: `glossary-cycle-data`

> The periodic job that totals a pool's tickets; when it marks a pool finalised, the engine starts working on it.

**Cycle data** is CycleDataDaemon's periodic run that totals each pool's tickets into units and prizes. When a pool is in play (or official/abandoned) it sets **`pools.cycledata_finalised`**; that change reaches the engine through Kafka and starts the pool there. Commingled pools are finalised together with the host.

---

## Fantasy pool
**Added**: 2026-10-09
**Updated**: 2026-10-09
**Id**: `glossary-fantasy-pool`

> A pool on player statistics, e.g. will this player go over or under 20.5 points; MVP pools instead ask which player does best.

A **Fantasy** pool extends SEP: each leg is a market on a **player metric** (points, goals, passes), and legs can use players from more than one sport event. Typical leg types are **over/under** (`FANTASY_OU`: will the player go over or under a line), **margin** (`FANTASY_MARGIN`) and pick'em-style picks.

Not to be confused with **MVP**, where a leg asks which of several players does best (`glossary-mvp`). Live player stats come from StatsFeedDaemon (SportsData); over/under threshold crossings can wait for ops approval (`fantasy_approvals`).

---

## Gateway
**Added**: 2026-10-09
**Id**: `glossary-gateway`

> One tote deployment (its own database and services) that can share pools with others, e.g. the UK or US tote.

A **gateway** is one tote installation taking part in commingling, listed in the commingling database's `gateways` table. Each has its own cbtote database, services and Kafka topics (`commingling.<gateway>`). Examples seen in data: production_uk, saprod, hulk, nebula.

---

## Leg
**Added**: 2026-10-09
**Id**: `glossary-leg`

> One question in a pool that the customer picks an answer for, e.g. one race or one match.

A **leg** is one part of a pool with its own selections and its own winner(s). In leg-per-event pools a leg is one sport event (a race, a match); in SEP, Fantasy and MVP pools a leg is a market on metrics (e.g. which player scores most points).

A ticket picks one or more selections in every leg; it wins if its picks are right in all legs (or enough legs for a consolation prize).

---

## Leg official
**Added**: 2026-10-09
**Id**: `glossary-leg-official`

> A leg is official when its result is final; a pool can only complete when all its legs are official.

**Leg official** (`LegOfficial`, in the engine's memory) is set when a leg's result is final. The engine uses it, not the database's `leg.official`, to decide shutdown. Every OFFICIAL event must reach its leg, or the pool stays in play.

---

## Leg-per-event pool
**Added**: 2026-10-09
**Id**: `glossary-leg-per-event-pool`

> The original pool type: each leg is one sport event (a race or a match), decided by its result.

In a **leg-per-event** pool, one leg = one sport event. Racing legs are decided by finishing positions; match legs by the match result (e.g. home/draw/away, correct score). The split with SEP is not "racing vs everything else"; see `pool-categories-domain-context`.

---

## Live offers
**Added**: 2026-10-09
**Id**: `glossary-live-offers`

> A price the engine offers a customer for their ticket while the pool is in play.

**Live offers** (`live_offers`) are per-ticket values the engine computes during a pool with the external offer generators and writes to cbtote; pools can enable them (`pools.offers`, `trading_enabled`). The engine also uses the same calculation to get the final payout.

---

## Market and market metrics
**Added**: 2026-10-09
**Updated**: 2026-10-09
**Id**: `glossary-market`

> A market is what a SEP/Fantasy leg is decided on (e.g. 'most corners'); its metrics are the stats that settle it.

A **market** links a leg to the statistic that decides it.

- **Metric values** are written by the feeds (e.g. StatsFeedDaemon) to **`market_metrics`** for MVP markets (`metric_value` per `sport_event_player_id`, with `favourite` and `manual_override`) or to **`market_results`** for other market types.
- **`market_histories.market_snapshot`** is a snapshot of the market at each change; the engine reads it (favourite, withdrawn players, values) to settle legs and calculate remaining units.

Market status (open, completed, official) comes from the event's market histories.

---

## Merchant (operator)
**Added**: 2026-10-09
**Id**: `glossary-merchant`

> The brand or operator a customer bets through, e.g. Colossus Bets or a partner bookmaker.

In the tote, a **merchant** (`merchants`) is the brand a customer belongs to; each operator has its own operator API host (`cbapi-<operator>`) and front end. The wallet also has a `merchants` table, but there it means a client system of the wallet; the two id spaces are unrelated.

---

## MVP pool
**Added**: 2026-10-09
**Id**: `glossary-mvp`

> A fantasy pool where each leg asks which player does best, and a leg can include players from several matches.

An **MVP** pool extends Fantasy: one leg can include players from **several sport events**, and the winner is the player with the best metric. MVP uses `market_metrics` (not `market_results`), and withdrawn players' units move to the leg's favourite.

---

## Pool
**Added**: 2026-10-09
**Updated**: 2026-10-09
**Id**: `glossary-pool`

> A pool is one bet product: a set of legs that customers pick selections for; its stakes form one prize pot.

A **pool** (`pools` table) is one bet product with a fixed number of legs (`leg_num`), a type (`type_code`), a schedule (`sched_start`) and a status. Customers' tickets on it form its pot.

**Statuses** (`pools.status`): `CREATED` → `OPEN` (taking bets) → `IN_PLAY` (first event started; no more bets) → `OFFICIAL` (results final, settled), or `ABANDONED`.

- `SUSPENDED` is defined in the engine and CbToteLogic, but no staging pool has it.
- `VOID` is a legacy status: 181 pools on staging, the latest from 2017; CycleDataDaemon still handles it.
- `COMPLETED` exists only as an engine constant: CbToteLogic's `PoolStatus` doesn't define it and no pool has it.

---

## Pool restart
**Added**: 2026-10-09
**Id**: `glossary-pool-restart`

> Re-running a pool's calculations from the start, e.g. after a late correction; expensive, so only done when needed.

A **pool restart** stops and restarts the engine's pool controllers, which then reprocess all the pool's sport event histories in order. It is requested from the console; CycleDataDaemon sends a `POOL_AMENDMENT` message that the engine acts on. Abandoning a leg that hasn't started must not restart the pool.

---

## Remaining units (RU)
**Added**: 2026-10-09
**Id**: `glossary-remaining-units`

> How many units are still alive (could still win) after each result; shown to customers as the pool progresses.

**Remaining units (RU)** are the units on lines that can still win, per prize, after the results so far. The engine (`RemUnitsController`) recalculates them on each sport event history and writes a row per step to `remaining_unit_histories` (**RU history**), which the front end shows.

Rules about when RU change (abandoned future legs, MVP COMPLETED vs OFFICIAL, withdrawals) are in `business/pools`.

---

## Selection, favourite and withdrawn
**Added**: 2026-10-09
**Id**: `glossary-selection`

> A selection is one possible answer in a leg (a runner, a team result, a player); a withdrawn selection's stakes move to the leg's favourite.

A **selection** is one possible outcome in a leg: a runner, a match result, a player. A ticket's `selections` lists its picks per leg.

- **Favourite:** the selection marked as favourite for the leg (racing: `sport_event_competitors.favourite`; MVP: `pool_favourite` in the market snapshot).
- **Withdrawn:** a selection taken out of the leg (non-runner, player out). Its units are moved to the favourite.

In the engine, selections are grouped in **bins** (e.g. favourite bin, withdrawn bin) when it calculates remaining units.

---

## SEP (Single Event Pool)
**Added**: 2026-10-09
**Id**: `glossary-sep`

> A pool whose legs are all about one sport event, decided by statistics (e.g. corners, player goals) rather than the final score.

A **Single Event Pool (SEP)** has several legs on one sport event. Each leg is a **market** whose result comes from metrics of that event (corners, goals, player passes), not the score. In code, match pool types (`CommonHelpers.MatchTypeCodes`, `IsMatchPool`) go through `SepEventsManager`. Fantasy and MVP pools build on SEP.

---

## Sport event and sport event history (SEH)
**Added**: 2026-10-09
**Updated**: 2026-10-09
**Id**: `glossary-sport-event-history`

> A sport event is a real match or race; each status or result change on it is recorded as a history row, which drives the engine.

A **sport event** (`sport_events`) is a real fixture: a race or a match. Each change on it is a **sport event history** (SEH, `sport_event_histories`) with an event code. SEH rows are written through CbToteLogic by the console, the stats feeds and CFS, and reach the engine through Kafka; the engine processes them in order to update remaining units.

**Event status flow:** `NOT_STARTED` → `IN_PLAY` ⇄ `BREAK` → `COMPLETED` → `OFFICIAL`, or `ABANDONED`.

**Event codes** cover status changes (`STARTED`, `COMPLETED`, `OFFICIAL`, `ABANDONED`, …) and also **stat updates** (`GOAL`, `CORNERS_UPD`, `F_MVP_UPD`, `FOU_UPD`, `PERIOD_CHANGE`, …) and amendment brackets (`AMENDMENT_START` / `AMENDMENT_END`). Stat updates drive remaining units too.

---

## Syndicate
**Added**: 2026-10-09
**Id**: `glossary-syndicate`

> A group bet: a manager creates a big ticket and other customers buy portions of it.

A **syndicate** (`syndicates`) is a ticket run by a **manager**, who sets the selections and stake; other customers buy portions (`tickets.syndicate_id`, `syndicate_portion`) and share any winnings. Managers can earn a rebate.

---

## Takeout
**Added**: 2026-10-09
**Updated**: 2026-10-09
**Id**: `glossary-takeout`

> The share of the pot the operator keeps before paying winners.

**Takeout** is the percentage taken from the pool's gross units before prizes are paid (gross → net units). It can be set at several levels:

- `pool_takeout_rates`: a rate for one pool;
- `custom_takeouts`: by sport, leg count, pool type, merchant, channel and date range (UK, non-UK and in-store rates);
- `merchant_takeouts` and `takeouts`: per merchant (and country).

---

## Tote (pool betting)
**Added**: 2026-10-09
**Id**: `glossary-tote`

> Pool betting: all stakes on a pool go into one pot, and after the operator's takeout the pot is shared among the winning tickets.

A **tote** (pari-mutuel) bet doesn't have fixed odds. Every stake on a pool goes into one pot; the takeout is removed and the rest is paid out to the winning tickets in proportion to their stake. Colossus Bets runs tote pools over several legs (racing, football, fantasy), with prizes for all legs right and, on some pools, consolation prizes.

Also used for one deployment of the system (a tote = one cbtote database and its services); see `glossary-gateway`.

---

## Units and lines
**Added**: 2026-10-09
**Id**: `glossary-units-and-lines`

> A line is one combination of picks (one per leg); units are how much is staked, counted per line and per ticket.

A **line** is one combination of one selection per leg. A ticket with several picks in some legs covers many lines (`tickets.lines`).

**Units** measure stake inside the tote: `tote_units_per_line` and `tote_units_per_ticket` on a ticket, and `num_units` / `num_units_gross` / `num_units_net` on the pool (gross before takeout, net after). Money amounts are kept separately (e.g. `stake_gbp`, `cost_gbp`).
