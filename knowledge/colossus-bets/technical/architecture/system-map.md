<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# System map

---

## Kafka topics: producers and consumers
**Added**: 2026-10-08
**Updated**: 2026-10-08
**Id**: `kafka-topics-map`

> Which service produces and consumes each Kafka topic (CDC of cbtote, engine/console status, tickets, commingling, statsfeed).

Topic names are configured per service and overridden by environment variables per tote, so prefixes vary (`db_master_json`, `db_tote`, `db_regional`, …). The shapes below are what the code uses.

| Topic | Produced by | Consumed by |
|-------|-------------|-------------|
| `<prefix>.cbtote.pools` | Debezium (CDC of `pools`) | Engine (pool start on `cycledata_finalised`), ConsoleLinux, TicketsPlacement (pool cache) |
| `<prefix>.cbtote.messages` | Debezium (CDC of `messages`, e.g. `POOL_AMENDMENT` from CycleDataDaemon) | Engine (pool controller restart), ConsoleLinux, TicketsPlacement |
| `<prefix>.cbtote.sport_event_histories` | Debezium; rows written through CbToteLogic `SpEvHistoryService` by ConsoleLinux, StatsFeedDaemon live fixture services and CFS guest receivers | Engine |
| `<prefix>.cbtote.custom_content_pool_histories` | Debezium | Engine |
| `<prefix>.cbtote.{sport_events, sport_event_competitors, legs, fantasy_approvals, approvals_event_competitor}` | Debezium | ConsoleLinux |
| `console.status.get_engine`, `console.status.get_pool` | ConsoleLinux | Engine |
| `tote_region_ovh.check.ticket` (`TicketCheckTopics`) | not in any C# repo; probably the Ruby tote API (unverified) | ConsoleLinux |
| `engine.status.engine`, `engine.status.pool` | Engine | ConsoleLinux |
| `<ticketPublishedTopicPrefix>.[<source>_]ticket` (e.g. `tote_region_ovh_fr.ticket`) | TicketsPlacement | not checked |
| Local commingling topic (`Kafka:LocalComminglingTopic`, e.g. `commingling.console`) | ConsoleLinux, CycleDataDaemon, cbstatsfeed, CbPaFeed | CFS on the same tote (every CFS runs a local and a global loop) |
| Global commingling topics (`commingling.<gateway>`) | CFS of the host tote | CFS of each guest tote (its own `commingling.<gateway>` topic) |
| `statsfeed.messagerouter.{fixture,team,player,prop}` (+ `.dlq`) | cbstatsfeed MessageRouter (off by default) | bb-tote |

Evidence: `enginelinux/ToteEngineLinux/appsettings.json` (Kafka section), `consolelinux/ConsoleLinux/appsettings.Staging.json` (incl. `TicketCheckTopics`), `consolelinux/ConsoleLinux/Services/KafkaConnector/KafkaJsonLoop.cs`, `comminglingfeedsystem/ComminglingFeedSystem/Services/Kafka/KafkaService.cs` (local and global loops), `ticketsplacement/TicketsPlacement/Services/Kafka/KafkaLoop.cs`, `comminglingfeedsystem/ComminglingFeedSystem/Helpers/KafkaTopicsHelper.cs`, `cbstatsfeed/CbStatsDaemon/appsettings.json`.

---

## Tote API, operator APIs, wallet and front ends
**Added**: 2026-10-08
**Id**: `tote-api-and-operator-layer`

> The Ruby tote and operator APIs, the wallet, BB tote, the front ends and the data warehouse, and their repos.

Above the tote back end sit the Ruby APIs and the front ends.

| Component | Does | Repo |
|-----------|------|------|
| **Tote API (cb-tote)** | Rails tote API (`v3`) on the tote MySQL; consumes CDC and commingling topics; replaces the older split of `tote-api-master` (central) and `tote-api-region` (regional replica, `v2`) | `colossus/ruby/cb-tote` |
| **Operator API (cbapi-core)** | Shared Rails engine gem: the server-side API behind the player UI, common to every operator; calls the tote API | `colossus/ruby/cbapi-core` |
| **Operator API hosts (`cbapi-<operator>`)** | One thin Rails app per operator (e.g. `cbapi-colossusbets`, `cbapi-matchbook`, `cbapi-hollywoodbets`) mounting cbapi-core with that operator's wallet connector, merchant id and currencies | `colossus/ruby/cbapi-colossusbets` (and siblings) |
| **Wallet (cb-wallet)** | Colossus Bets customer wallet: accounts, merchant API, transactions, CRM UI | `colossus/ruby/cb-wallet` |
| **BB tote** | Back end of the player-props (BB / bet builder) product; reads cbtote read-only, consumes the statsfeed MessageRouter topics | `colossus/ruby/bb-tote` |
| **Front ends (nx-colossus)** | Nx monorepo of the Angular web apps (one per operator) and Ionic/Capacitor mobile apps | `colossus/javascript/nx-colossus` |
| **Data warehouse** | AWS Glue ETLs from cbtote/wallet data into Redshift (`reporting` / `data-warehouse`), plus reports | `colossus/data-warehouse/data-warehouse-scripts` |

From READMEs, Gemfiles and config, not verified against running systems.

---

## Tote back-end services and repos
**Added**: 2026-10-08
**Updated**: 2026-10-08
**Id**: `tote-backend-services-map`

> The C# services around the cbtote database, what each does, its repo, and the path of a pool from creation to settlement.

The tote back end is a set of C# services around one MySQL database, **cbtote**. Change data capture (Debezium) streams cbtote tables to Kafka, which is how the services react to each other's writes.

| Component | Does | Repo |
|-----------|------|------|
| **ConsoleLinux** | Ops back office (API + Angular): fixtures, pools, results, approvals, engine status. Runs the pool closure, settlement and abandonment loops | `colossus/c_sharp/consolelinux` |
| **CbToteLogic** | Shared library (git submodule) with the cbtote EF model and pool/fixture logic, used by ConsoleLinux, CycleDataDaemon, cbstatsfeed, CFS and CbPaFeed | `colossus/c_sharp/CbToteLogic` |
| **CycleDataDaemon** | Timer worker: aggregates tickets into pool units and prizes; sets `pools.cycledata_finalised`, which makes the engine start the pool (commingled pools are finalised together with the host through `ComminglingFinaliseManager` instead); writes `POOL_AMENDMENT` messages for controller restarts | `colossus/c_sharp/cycledatadaemon` |
| **ToteEngineLinux** (engine) | One controller set per pool: remaining units, offers, winning selections and payouts, written to cbtote. Offers come from external executables it starts as separate processes (below) | `colossus/c_sharp/enginelinux` |
| **Offer generators** | External executables the engine runs per pool to compute offers: sport, fecta and placepot variants, downloaded into the engine image at build time | `offer-generator/offer_generator`, `offer-generator/offer_generator_fecta`, `offer-generator/offer_generator_placepot` |
| **SepProxy** | External executable the engine runs for SEP pools | `offer-generator/SepProxy` |
| **TicketsPlacement** | Bet-placement HTTP API (`POST /tickets`): HMAC auth, validates against cached pools, inserts tickets, publishes placed tickets to Kafka | `colossus/c_sharp/ticketsplacement` |
| **ComminglingFeedSystem** (CFS) | Replicates host-tote actions to guest totes via the local and global commingling topics and S3 | `colossus/c_sharp/comminglingfeedsystem` |
| **StatsFeedDaemon** | Polls SportsData.io, stores stats in the stats_feed DB, writes fixtures/players/metrics to cbtote; repo also has the stats public API and admin console | `colossus/c_sharp/cbstatsfeed` |
| **CbPaFeed** | Receives the PA racing feed and writes it to cbtote (replaces the Rails cb-pa-feed) | `colossus/c_sharp/cbpafeed` |
| **SepCorrelationAlgorithm** | Library: correlated selections in SEP pools, ticket compression; submodule of the engine | `colossus/c_sharp/sepcorrelationalgorithm` |
| **cbtote database** | Schema source of truth (DDL + `changes/`); `develop` = staging, `master` = production. Also the commingling, console and cashing schemas | `colossus/c_sharp/cbtote-schema` |
| **Debezium CDC** | Kafka Connect + Debezium MySQL connector on EKS producing `<prefix>.cbtote.<table>` topics | `colossus/devops/kafka-connector` |

**Main flow of a pool:** Console (or a feed) creates fixtures and the pool in cbtote → TicketsPlacement takes tickets → CycleDataDaemon aggregates units and, once the pool is in play, sets `cycledata_finalised` (for a commingled pool, together with the host via `ComminglingFinaliseManager`) → CDC on `pools` → the engine starts the pool controllers and keeps remaining units and offers → event status changes and results reach the engine as `sport_event_histories` rows (CDC) → Console runs closure and settlement; the engine writes winners and payouts.

**Who writes `sport_event_histories`:** CbToteLogic's `SpEvHistoryService`, called from `FixtureStatusService`, `FixtureResultService`, `MarketStatusService` and `FantasyMarketService`. Those are used by ConsoleLinux (operators), StatsFeedDaemon's live fixture services (`NflLiveFixtureService`, `NbaLiveFixtureService`, `MlbLiveFixtureService`, `NhlLiveFixtureService`, `CbbLiveFixtureService`: live fantasy/MVP results) and CFS's guest receivers (`FantasyAmendmentReceiverService`, `FantasyAbandonmentReceiverService`, …: commingled results). So results reach the engine from feeds and other totes, not only from the console.

Kafka topic names come from each service's config and are overridden per tote on the pod, so the prefixes differ between totes; see `kafka-topics-map`.
