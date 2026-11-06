<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Business Knowledge Index

Business rules and domain logic.

**Last Updated**: 2026-10-09

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [glossary.md](glossary.md) | Glossary | 2026-10-09 | 2026-10-09 | Domain terms for PMs and engineers (SEP, MVP, RU, commingling host/guest, leg official, ...). |
| [pools.md](pools.md) | Pool Business Rules | 2026-01-23 | 2026-01-28 | Tote pool rules: pool categories (leg-per-event, SEP, Fantasy, MVP), withdrawals, favourites, unit allocation, event ordering, pool restarts. |

## Quick Reference
- BB / bet builder / player props / bb_tote: glossary.md - The player-props product: customers build entries on player statistics; it has its own back end (bb-tote).
- commingling / commingled / host / guest / CFS: glossary.md - Sharing one pool across several totes so their customers bet into the same pot; the tote that owns the pool is the host, the others are guests.
- completed / official / weighed in / settled: glossary.md - Completed means the event has finished; official means the result is final and can be paid out.
- cycle data / cycledata_finalised / CycleDataDaemon: glossary.md - The periodic job that totals a pool's tickets; when it marks a pool finalised, the engine starts working on it.
- fantasy / player metrics / over under / FANTASY_OU / FANTASY_MARGIN / pick'em: glossary.md - A pool on player statistics, e.g. will this player go over or under 20.5 points; MVP pools instead ask which player does best.
- gateway / tote instance / region: glossary.md - One tote deployment (its own database and services) that can share pools with others, e.g. the UK or US tote.
- leg / legs / leg order: glossary.md - One question in a pool that the customer picks an answer for, e.g. one race or one match.
- leg official / LegOfficial / shutdown: glossary.md - A leg is official when its result is final; a pool can only complete when all its legs are official.
- leg-per-event / racing pool / match pool: glossary.md - The original pool type: each leg is one sport event (a race or a match), decided by its result.
- live offers / cash out / trading / offer generator: glossary.md - A price the engine offers a customer for their ticket while the pool is in play.
- market / market metrics / market_snapshot / market histories: glossary.md - A market is what a SEP/Fantasy leg is decided on (e.g. 'most corners'); its metrics are the stats that settle it.
- merchant / operator / brand / white label: glossary.md - The brand or operator a customer bets through, e.g. Colossus Bets or a partner bookmaker.
- MVP / FANTASY_MVP / most valuable player: glossary.md - A fantasy pool where each leg asks which player does best, and a leg can include players from several matches.
- pool / pool status / open / in play / official / abandoned: glossary.md - A pool is one bet product: a set of legs that customers pick selections for; its stakes form one prize pot.
- pool restart / controller restart / POOL_AMENDMENT / reload_tickets: glossary.md - Re-running a pool's calculations from the start, e.g. after a late correction; expensive, so only done when needed.
- remaining units / RU / RU history / remaining_unit_histories: glossary.md - How many units are still alive (could still win) after each result; shown to customers as the pool progresses.
- selection / favourite / favorite / withdrawn / non-runner / bin: glossary.md - A selection is one possible answer in a leg (a runner, a team result, a player); a withdrawn selection's stakes move to the leg's favourite.
- SEP / single event pool / match pool: glossary.md - A pool whose legs are all about one sport event, decided by statistics (e.g. corners, player goals) rather than the final score.
- sport event / sport event history / SEH / event code / sport_event_histories: glossary.md - A sport event is a real match or race; each status or result change on it is recorded as a history row, which drives the engine.
- syndicate / manager / portion / group bet: glossary.md - A group bet: a manager creates a big ticket and other customers buy portions of it.
- takeout / commission / margin / net units: glossary.md - The share of the pot the operator keeps before paying winners.
- tote / pari-mutuel / pool betting: glossary.md - Pool betting: all stakes on a pool go into one pot, and after the operator's takeout the pot is shared among the winning tickets.
- units / lines / units per line / gross / net: glossary.md - A line is one combination of picks (one per leg); units are how much is staked, counted per line and per ticket.
- abandoned: pools.md - Abandoning a future leg (a leg that hasn't started) does not change remaining units.
- SEP / MVP / abandoned / OFFICIAL / MVP RU: pools.md - Remaining units and ticket distributions must be updated when all sport events of a leg are in a terminal state (Completed, Official, or Abandoned).
- pools / SEP / OFFICIAL: pools.md - For match/SEP pools, an OFFICIAL sport event history must always be processed as a score/settlement update for the affected leg.
- pools / pool categories / SEP / leg-per-event / Fantasy / MVP: pools.md - There are two main pool categories; the split is not "SEP vs racing".
- abandoned / pool restart: pools.md - Abandoning a sport event in an unstarted leg should NOT restart the pool.
- pool restart: pools.md - When restarting a pool, sport event histories must be processed in chronological order (by SEH.id ASC or SEH.created_at ASC).
- pools / SEP / Fantasy / MVP / markets (SEP): pools.md - SEP pools link legs to metrics through markets rather than event results; Fantasy extends SEP with player metrics across events, and MVP extends Fantasy.
- started event / abandoned / OFFICIAL: pools.md - STARTED events must be the first events chronologically.
- pools / MVP / withdrawals / OFFICIAL: pools.md - When a player or runner is withdrawn from a pool leg, their units must be moved to the favourite player/runner for that leg.

## Parent
- [../index.md](../index.md)
