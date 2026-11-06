<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Engine pool controllers restart flow

**Added**: 2026-02-13
**Context**: End-to-end sequence for restarting a pool controller (console → cycle data → messages topic → engine).
**Id**: `engine-pool-controllers-restart-flow`

> A pool controller restart runs Console → ReloadTicketsForPool → cycle data → POOL_AMENDMENT on the messages topic → the engine restarts the pool's controllers.

**Source**: Manuel Zulian, 20 Apr 2021 (Confluence)

To restart a pool controller, the following sequence happens in order:

1. **Console** triggers the restart via `PoolService.RestartPoolController` in cbtotelogic. The console sets **`reload_tickets`** (and **`cycledata_finalised`** to false) when requesting a pool controller restart.
2. **PoolService.RestartPoolController** calls **PoolTicketService.ReloadTicketsForPool**, which effectively "resets" the pool for the cycle data service (and may refresh units).
3. **Cycle data** picks up the pool on the next cycle (every 15 seconds) and finalises it again. If **`reload_tickets`** is true, cycle data writes a row in the **messages** table with event code **POOL_AMENDMENT** (SendMessages). That amendment message is what triggers the pool controller restart in the engine. Field casing in this message must match what the engine expects.
4. **Engine** consumes the **messages** Kafka topic; when a POOL_AMENDMENT is received it shuts down the two controllers for that pool and starts two new ones. The engine should **eventually set `reload_tickets` to false** after receiving and handling that message (see reload-tickets-flag.md).

**Notes:**

- POOL_AMENDMENT is sent **only by cycle data**; the console never sends it directly.
- **Pool controller restart** is driven by the **messages** Kafka topic. **Normal pool start** is driven by the **pools** Kafka topic.
