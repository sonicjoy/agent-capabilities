<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Pool start sequence

Cycle Data Daemon normal start vs restart, engine pool start, commingling host and guest replication.

---

## Commingling pool replication sequence (CFS)
**Added**: 2026-02-16
**Updated**: 2026-02-16
**Context**: How a pool created or updated on the host console is replicated to guest totes via the Commingling Feed System (comminglingfeedsystem codebase). This is the “pool start” from a commingling perspective: host pool → shared S3 + global Kafka → guest pool created and ready for cycle data / engine.
**Id**: `commingling-pool-replication`

> A change to a commingled pool is replicated from the host tote to guest totes: the host CFS collects it, stores it in S3 and publishes it globally, and each guest CFS recreates competitors, sport events and the pool.

**Trigger:** Console (or CFS guest receiving an update) creates or updates a pool in the tote DB. If the pool is commingled (`originalPool.CommingledPool != null`), **CbToteLogic** `PoolCreationService.UpdateAndSavePool` raises a **PoolChangedLocalMessage** (operation `ConsoleToHost.PoolChanged` / `local.pool_created`) to the **local** commingling Kafka topic.

**Host (CFS):**

1. **Local Kafka** → CFS consumes from **local** commingling topic → **MessageQueue** → **Dispatcher** → `PoolSharingService.SharePool(PoolChangedLocalMessage)`.
2. **PoolSharingService**:
   - **PoolDataCollector.GetPoolModel(poolId)** — build in-memory pool representation (CommingledPoolPackage: pool, legs, prizes, FX, etc.).
   - **PoolSerializer.SerializePool** — JSON.
   - **IPoolTransfer.PublishPool** — upload JSON to S3, return file name.
   - Create **SharedPool** (and **SharedPoolGateway**, **SharedPoolInfo**) in **commingling** DB.
   - Build **PoolPublishedGlobalMessage** (PoolId, PoolFileName, ToteOrigin, etc.).
   - For each **gateway** (except self): if pool category allowed and gateway active → **IKafkaPublisher.PublishGlobal**(gateway topic, message); create SharedPoolGateway/SharedPoolInfo.
   - For host gateway: set TotePoolId, SharedPoolGateway, SharedPoolInfo; **SaveChanges**.
3. **Global Kafka** — Each guest tote’s CFS consumes from the **global** commingling topic (per-gateway or shared).

**Guest (CFS):**

4. **Global Kafka** → CFS consumes **PoolPublishedGlobalMessage** → **Dispatcher** → `PoolReceiverService.UpsertPool(PoolPublishedGlobalMessage)`.
5. **PoolReceiverService**:
   - **IPoolTransfer.RetrievePool(PoolFileName)** — get JSON from S3; deserialize **CommingledPoolPackage**.
   - Check **IsPoolCategoryAvailable** for local gateway; get **IPoolGroupService.GetDefaultPoolGroup**.
   - **CompetitorsReplicationService.CreateOrUpdate(hostCompetitors)** — create/update competitors; **must be before sport events**.
   - **SportEventsReplicationService.CreateOrUpdate(hostSportEvents)** — create/update sport events; **must be before pool creation**.
   - If MVP pool: **MvpMarketReplicationService.CreateOrUpdate(hostMarkets)**.
   - **BuildPoolViewModel(cpp)**; **MapHostIdsToGuest** (or MapHostIdsToGuestMvp) — replace host IDs using commingled_* mapping tables.
   - **ISportSubCodeService.ProcessSportSubCode**.
   - **IPoolCreationService.UpdateAndSavePool(pm, PoolFxRates, Cfs)** — creates/updates pool on guest tote.
   - **PopulateComminglingInformation**; **UpdateSharedPoolWithGuestId** in commingling DB (SharedPoolGateway.TotePoolId, etc.).

**Order on guest:** Competitors → Sport events → (MVP markets) → ID mapping → Pool creation → Shared DB update. Entity creation order is required so pool creation can resolve guest competitor/sport_event IDs via commingled_* tables (external_id = host id).

**Implementation:** **CbToteLogic**: `PoolCreationService.UpdateAndSavePool` (raises PoolChangedLocalMessage). **ComminglingFeedSystem**: `KafkaService` (local + global loops), `MessageQueue`, `Dispatcher`, `PoolSharingService`, `PoolDataCollector`, `PoolSerializer`, `PoolReceiverService`, `CompetitorsReplicationService`, `SportEventsReplicationService`, `MvpMarketReplicationService`, `PoolCreationService` (CbToteLogic), S3 via `IPoolTransfer`, commingling DB (SharedPool, SharedPoolGateway, SharedPoolInfo). **Conventions:** commingled_* tables, external_id = host entity id; is_local for host.

---

## Cycle data (engine view)
**Added**: 2026-02-16
**Id**: `cycle-data-engine-view`

The engine does not define or build “cycle data”; it only reacts to it. From the engine’s perspective:

- **`cycledata_finalised`** is a boolean column on the **pools** table. When the console/cycle data daemon sets it to **true**, that means the pool’s cycle data (legs, events, competitors, units, etc.) is final and the engine is allowed to take over.
- The **pools** table is streamed to Kafka (e.g. Debezium CDC). The engine’s **PoolsListener** subscribes to the pools topic and, when it sees a row change where **`cycledata_finalised`** is in the changed columns, builds an internal message:
  - If **cycledata_finalised** became **true** → `event_code = CYCLEDATA_FINALISED` → engine calls **StartPoolAsync(poolId)** and starts the pool (load tickets, start PoolManager, RemUnitsController, OfferController).
  - If it became **false** → `event_code = CYCLEDATA_UNFINALISED` → no start; engine does not stop an already-running pool from this event.
- The engine also uses **cycledata_finalised** when reporting status (e.g. **EngineStatusMessage**, **PoolStatusMessage**) and in **ReOpenPool** logic (after clearing RU histories and ticket distributions, if status is not OPEN or cycledata is already finalised, the engine calls **ReOpenPoolAsync** and sets pool status to OPEN).

So “before pool starts” on the engine side: the pool exists with **cycledata_finalised = false**. The console/cycle data daemon finalises the pool (sets **cycledata_finalised = true**); that change is streamed to the pools topic; the engine receives it and starts the pool. The engine does not start pools that are still OPEN and not yet cycle-data-finalised—they are not in the in-play list at startup (see below).

---

## Engine pool start sequence
**Added**: 2026-02-16
**Id**: `engine-pool-start-sequence`

This section describes how the **engine** (ToteEngineLinux) starts a pool: at process startup (in-play pools) and when it receives **CYCLEDATA_FINALISED** from the pools topic.

### 1. Engine startup (ToteController)

1. **ToteController** starts and runs **Initialise()**.
2. **Initialise()** loads shared config (match type codes, fantasy metrics, commingling gateways if enabled), then:
   - Calls **StartAllInPlayPools()** (start pools already in play).
   - Then **ProcessPreviousExistingHistories()** (sport event histories created while the engine was down).

### 2. Start in-play pools (StartAllInPlayPools)

1. **Get in-play pools**: **GetInPlayPoolsAsync()** — pools where `pool_finalised = 0` and `status` is **not** in `OPEN`, `OFFICIAL`, `VOID`, `CREATED`, `ABANDONED`. So only pools that have already left OPEN (e.g. IN_PLAY) are started at engine startup.
2. **Filter**: **PoolsHandlingHelper.ShouldHandleThisPool()** (per-instance config).
3. **Start each**: For each handled pool, **StartPoolAsync(pool)** is called (with a semaphore to limit concurrency).

### 3. Start pool when CYCLEDATA_FINALISED (live)

When the engine processes a **POOLS** channel message with **event_code = CYCLEDATA_FINALISED** (from PoolsListener after **cycledata_finalised** flips to true in the DB), it calls **StartPoolAsync(poolId)**. That overload loads the pool by ID, checks **ShouldHandleThisPool** and that **status == IN_PLAY**, then calls **StartPoolAsync(pool)** with the loaded **PoolObj**.

### 4. Start a single pool (StartPoolAsync(PoolObj pool))

1. **Load tickets**: Commingling → own gateway tickets from DB + **ExternalTicketsService.GetTickets()**; else **GetTicketsForPoolAsync(pool.id)**.
2. **Guard**: If **\_controllers** already contains this pool id, log and return.
3. **Create controller**: Resolve **IPoolManager**, store in **\_controllers[pool.id]**.
4. **Start**: **await _controllers[pool.id].StartAsync(pool)**.

### 5. PoolManager.StartAsync(pool)

1. **RemUnitsController**: **\_ruCtrl.Start(_pool, _cancellationToken)** — builds pool context (**CreatePoolContextAsync**: legs, correlations, selection templates for match pools, sport event IDs), then starts **RuCtrlThread()** on a background task.
2. **OfferController**: **\_offerCtrl.Start(_pool, _cancellationToken)** (runs in parallel).
3. **await Task.WhenAll([ruTask, oTask])** so both are started before **StartAsync** returns.

### 6. RemUnitsController thread (per pool)

1. **RuCtrlThread()**:
   - **Replay**: **ProcessPreviousExistingHistory()** — deletes existing rem unit histories and ticket distributions for this pool, loads sport event histories in **chronological order** (**created_at ASC**), replays each through the same path as live (event sourcing).
   - Then enters the **message loop**: take messages from the queue until **AreAllSportEventsOfficial()**; for each message run the flow strategy (**ProcessSepHistory** / **ProcessSportEventHistory**) and **UpdateRemainingUnits**.

**Implementation**: **ToteController** (Initialise, StartAllInPlayPools, StartPoolAsync, message switch for CYCLEDATA_FINALISED), **PoolManager.StartAsync**, **RemUnitsController.Start** / **RuCtrlThread** / **ProcessPreviousExistingHistory**, **PoolsListener.ProcessCycleDataFinalisedChange**, **DataAccessLayer.GetInPlayPoolsAsync**, **DataAccessLayer.GetSpEventHistoriesForPoolAsync** (order by **created_at ASC**).

---

## Pool start sequence (Cycle Data Daemon)
**Added**: 2026-02-16
**Context**: Recording the end-to-end sequence that leads to normal pool start vs pool controller restart (cycledatadaemon codebase and knowledge).
**Id**: `pool-start-sequence-cycle-data-daemon`

> Cycle data finalises a pool (cycledata_finalised) and the pools Kafka topic makes the engine start it; a controller restart is a separate flow via POOL_AMENDMENT.

**Two distinct flows:**

1. **Normal pool start** – Engine starts the pool when cycle data has “finalised” the pool. Trigger: **pools** Kafka topic (e.g. Debezium from `pools` table); the engine watches for **`cycledata_finalised`** being set.
2. **Pool controller restart** – Console requests a restart; cycle data sends POOL_AMENDMENT; engine restarts the two pool controllers. Trigger: **messages** Kafka topic (see pool-controller-restart-flow.md).

**Normal pool start sequence (Cycle Data Daemon):**

1. **Worker** – Runs on a timer (`CycleSpan` from config). Each tick creates a scope and calls `ICycleDataController.RunAsync()`.
2. **CycleDataController.RunAsync()** – Gets `GetPoolAndTicketDataAsync()`, then for each `(poolId, accPool)` runs `ToteUpdateService.HandlePoolAsync(poolId, accPool)` in parallel.
3. **ToteRepository.GetPoolAndTicketDataAsync()** – Selects pools where `!CycledataFinalised` OR (`ReloadTickets && !PoolFinalised`). Loads pool + legs/selections, then tickets; aggregates to `AccPool` (NumUnits, NumUnitsNet, NumUnitsGross) per pool.
4. **ToteUpdateService.HandlePoolAsync(poolId, accumulatedPool)** – If commingling: process commingling. `DataCheckService.NeedUpdate`: true if reload_tickets, or status InPlay/Official/Abandoned/VOID, or unit delta above threshold. If no update: return. Update pool prizes, then **UpdateToteAsync**: write units; if status is InPlay/Official/Abandoned/VOID set **CycledataFinalised = true** (or enqueue commingling finalise). Save to DB. For non-commingled: if NeedsReloading send POOL_AMENDMENT (restart flow); if NeedsToResetReloadTickets clear reload_tickets.
5. **Trigger for normal pool start** – The **`cycledata_finalised`** flag set in the **pools** table is streamed (e.g. Debezium) to the **pools** Kafka topic; the engine consumes that to start the pool. POOL_AMENDMENT is for **restart** only (ToteUpdateService.cs ~157–159).

**Key distinction:** Normal pool start = **pools** topic / `cycledata_finalised`. Pool controller restart = **messages** topic / POOL_AMENDMENT.
