<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# reload_tickets flag cleared by engine

**Added**: 2026-02-13
**Updated**: 2026-02-13
**Context**: Recording who sets/clears reload_tickets in the pool controller restart flow.
**Id**: `reload-tickets-flag-cleared-by-engine`

> The console sets reload_tickets when it requests a pool controller restart; the engine clears it after handling the resulting POOL_AMENDMENT.

**Who sets it:** The **console** sets **`reload_tickets`** (and **`cycledata_finalised`** to false) when requesting a pool controller restart. Cycle data then picks up the pool, finalises it again, and if `reload_tickets` is true sends a POOL_AMENDMENT message to the engine (see pool-controller-restart-flow.md).

**Who clears it:** The **engine** should eventually set **`reload_tickets`** to false after receiving and handling the POOL_AMENDMENT message. The engine does this by calling **`DataAccessLayer.UpdatePoolReloadTicketsFlag(poolId)`** (default `reload = false`), which runs `UPDATE pools SET reload_tickets=0, updated_at=utc_timestamp WHERE id=@poolId`.

**Where it is called**: `ToteEngineLinux/DAL/DataAccessLayer.cs` — inside both overloads of `GetTicketsForPoolAsync` (after loading tickets for the pool), at lines 1273 and 1320. So whenever the engine loads tickets for a pool, it then clears the flag.

**Method**: `UpdatePoolReloadTicketsFlag(int poolId, bool reload = false)` (around line 1017).
