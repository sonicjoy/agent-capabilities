<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Commingling ticket files: upload, bucket, and TicketsReady

**Added**: 2026-02-23
**Context**: Technical details for commingling ticket file upload (CFS) and readiness check (CycleDataDaemon). Important for multi-gateway commingling and "Maximum retry count exceeded waiting for ticket files" issues.
**Id**: `commingling-ticket-files-shared-bucket`

> All gateways that share a pool must upload ticket files to the same S3 bucket.

## Same bucket for all gateways

**All gateways that share a pool must upload ticket files to the same S3 bucket.**

- CycleDataDaemon uses a single bucket (`TicketsBucketName` in its config) and does one `ListObjectsV2` with prefix `tickets/{year}/{month}/{hostPoolId}_{hostGateway}/`.
- It then checks that every shared gateway's two files (solo + syndicate) exist in that result set.
- If any gateway uploaded to a different bucket, its keys would never appear and `TicketsReady` would stay false.
- **Deployment**: Each CFS instance (UK tote, Nebula, Hulk, etc.) must be configured with the same `TicketsBucketName` (and same region) so all files land where CycleDataDaemon looks.

## Where sharedPools (gateways list) comes from

- **Source**: Commingling DB → `SharedPools` → `SharedPoolGateways` (where `Shared == true`).
- **Built in**: CycleDataDaemon `ComminglingFinaliseManager.StartFinalising`: loads the `SharedPool` for the host pool (`TotePoolId == request.ExternalId`, `Gateway.Name == request.Gateway`), then `gateways = sharedPool.SharedPoolGateways.Where(pg => pg.Shared).Select(pg => (pg.Gateway.Name, pg.TotePoolId)).ToList()`.
- **Passed**: Manager → `ComminglingFinaliseService.FinalisePool(request, gateways)` → `WaitForTicketFiles(poolId, gateways)` → `TicketsFileCheckService.TicketsReady(poolInfo, gateways)` (second parameter is the "sharedPools" list).
- So the list is **all gateways that are marked as shared for this commingled pool** in the commingling database, plus their guest pool id (`TotePoolId`).

## TicketsReady check (exact logic)

**Location**: CycleDataDaemon `TicketsFileCheckService.TicketsReady`.

1. **Prefix**: `tickets/{year}/{month}/{hostPoolId}_{hostGateway}/` (e.g. `tickets/2026/2/51453_staging-uk/`).
2. **List S3**: One `ListObjectsV2` on the configured bucket with that prefix; keys returned → `HashSet<string> s3Files`.
3. **Per gateway** in `sharedPools`: require **both** keys present in `s3Files`:
   - Solo: `tickets/{y}/{m}/{hostPoolId}_{hostGateway}/tickets_{localPoolId}_{gateway}_for_{hostPoolId}_{hostGateway}.csv`
   - Syndicate: `tickets/{y}/{m}/{hostPoolId}_{hostGateway}/syndicate_portions_{localPoolId}_{gateway}_for_{hostPoolId}_{hostGateway}.csv`
4. **Return**: `true` only if **every** shared gateway has **both** files in the list; otherwise `false`. No content or size check—key existence only.

## File naming (CFS and CycleDataDaemon must match)

- CFS: `ComminglingFeedSystem.Helpers.UploadHelper` (and `S3TicketFileUploader` uses it).
- CycleDataDaemon: `TicketsFileCheckService` static methods `GetSoloTicketsFileName` / `GetSyndicateTicketsFileName`.
- Formula is the same: `hostPoolId`, `guestPoolId` (local pool id), `hostGateway`, `guestGateway` (gateway name), `timestamp` = host pool scheduled start.

## Implication for multi-gateway commingling

- **TicketsReady requires files from every gateway** in `SharedPoolGateways` where `Shared == true`.
- If the pool is shared with UK tote, Nebula, and Hulk, then UK, Nebula, and Hulk must each have CFS running and uploading their ticket files to the **same** bucket when they process `pool_closed`; otherwise CycleDataDaemon will never see "tickets ready" and will retry until max count (e.g. 120) then throw.
- In environments where only one gateway runs (e.g. staging with only UK CFS), either only that gateway should be marked shared for that pool, or CycleDataDaemon would need a different rule (e.g. require only current gateway's files) for that environment.
