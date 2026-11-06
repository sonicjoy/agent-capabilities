<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Architecture Knowledge Index

System architecture and event flow.

**Last Updated**: 2026-10-08

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [commingling.md](commingling.md) | Commingling (general) | 2026-02-16 | - | Replicating host actions to guest totes: local vs global Kafka, host/guest roles, commingled_* mapping, CFS and console roles. |
| [commingling-ticket-files.md](commingling-ticket-files.md) | Commingling ticket files | 2026-02-23 | - | Upload bucket shared by all gateways, sharedPools from SharedPoolGateways, TicketsReady logic, file naming. |
| [event-flow.md](event-flow.md) | Sport Event History Flow | 2026-01-23 | - | Sport event status changes flow Console → Kafka → Engine. |
| [merchant-id-spaces.md](merchant-id-spaces.md) | Tote vs wallet merchant IDs (BB / Fantasy) | 2026-08-18 | - | Tote 255 Fantasy is the brand; wallet 1 fantasyprod is the wallet client. Never join the two id spaces. |
| [pool-controller-restart-flow.md](pool-controller-restart-flow.md) | Engine pool controllers restart flow | 2026-02-13 | - | Console → ReloadTicketsForPool → cycle data → POOL_AMENDMENT → engine restarts controllers. |
| [pool-start-sequence.md](pool-start-sequence.md) | Pool start sequence | 2026-02-16 | 2026-02-16 | Cycle Data Daemon normal start vs restart, engine pool start, commingling host and guest replication. |
| [reload-tickets-flag.md](reload-tickets-flag.md) | reload_tickets flag | 2026-02-13 | 2026-02-13 | Console sets the flag; the engine clears it after handling POOL_AMENDMENT. |
| [rem-units-controller.md](rem-units-controller.md) | RemUnitsController and SEP behaviour | 2026-02-06 | 2026-02-10 | MarketHistories, LegOfficial, remaining-unit skip rules, strategy split (is_match_kind). |
| [statsfeed-daemon.md](statsfeed-daemon.md) | StatsFeedDaemon | 2026-01-27 | 2026-01-27 | How player and event stats reach stats_feed and cbtote; ToteMetricsService conditions. |
| [system-map.md](system-map.md) | System map | 2026-10-08 | 2026-10-08 | - |

## Quick Reference
- commingling: commingling.md - Replicate actions done on a host console to guest consoles in a fan-out manner.
- ticket files (commingling) / TicketsReady: commingling-ticket-files.md - All gateways that share a pool must upload ticket files to the same S3 bucket.
- event flow / kafka / console / racing status: event-flow.md - Sport event status changes flow from the console through the database and Kafka to the engine (enginelinux).
- BB / Fantasy merchant IDs / merchant IDs (BB): merchant-id-spaces.md - Tote/bb_tote merchants are brands.
- pool controller restart / POOL_AMENDMENT: pool-controller-restart-flow.md - A pool controller restart runs Console → ReloadTicketsForPool → cycle data → POOL_AMENDMENT on the messages topic → the engine restarts the pool's controllers.
- commingling pool replication: pool-start-sequence.md - A change to a commingled pool is replicated from the host tote to guest totes: the host CFS collects it, stores it in S3 and publishes it globally, and each guest CFS recreates competitors, sport events and the pool.
- cycledata_finalised: pool-start-sequence.md - The engine does not define or build “cycle data”; it only reacts to it.
- cycledata_finalised: pool-start-sequence.md - This section describes how the engine (ToteEngineLinux) starts a pool: at process startup (in-play pools) and when it receives CYCLEDATA_FINALISED from the pools topic.
- cycledata_finalised / pool start (normal): pool-start-sequence.md - Cycle data finalises a pool (cycledata_finalised) and the pools Kafka topic makes the engine start it; a controller restart is a separate flow via POOL_AMENDMENT.
- reload_tickets: reload-tickets-flag.md - The console sets reload_tickets when it requests a pool controller restart; the engine clears it after handling the resulting POOL_AMENDMENT.
- RemUnitsController: rem-units-controller.md - Don't reload the pool from the DB on each sport event history message: GetPoolAsync doesn't load TicketList, so units stay 0; use the pool given at start.
- RemUnitsController: rem-units-controller.md - RemUnitsController no longer branches on IsMatchPool for processing.
- RemUnitsController: rem-units-controller.md - RemUnitsController shutdown is based only on in-memory _ruCtrlContext.LegOfficial (set when we process OFFICIAL/ABANDONED and set settled = true).
- RemUnitsController / strategy split: rem-units-controller.md - Match pools (type_code with is_match_kind = 1) use MarketBasedPoolEventFlowStrategy; all other pools use SportEventBasedPoolEventFlowStrategy.
- RemUnitsController / RU history skip: rem-units-controller.md - All rules for skipping a remaining-unit history row live in one method, ShouldSkipRemUnitHistoryRow; amendments are never skipped.
- StatsFeedDaemon: statsfeed-daemon.md - StatsFeedDaemon downloads SportsData stats into stats_feed and writes metrics to cbtote only for markets used in pools.
- kafka / topics / debezium / cdc / commingling topic / engine status: system-map.md - Which service produces and consumes each Kafka topic (CDC of cbtote, engine/console status, tickets, commingling, statsfeed).
- tote api / cb-tote / cbapi / operator / wallet / bb-tote / nx-colossus / data warehouse: system-map.md - The Ruby tote and operator APIs, the wallet, BB tote, the front ends and the data warehouse, and their repos.
- architecture / services / repos / engine / console / cycledata / ticketsplacement / cfs / statsfeed: system-map.md - The C# services around the cbtote database, what each does, its repo, and the path of a pool from creation to settlement.

## Parent
- [../index.md](../index.md)
