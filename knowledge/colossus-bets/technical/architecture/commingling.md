<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Commingling (general)

**Added**: 2026-02-16
**Context**: What commingling does in general across the system (console, CFS, engine). Commingling = replicating console actions from one tote (host) to other totes (guests) so they stay in sync for shared pools (e.g. same pool offered on multiple totes).
**Id**: `commingling-general`

> Replicate actions done on a host console to guest consoles in a fan-out manner.

## Purpose

- **Replicate** actions done on a **host** console to **guest** consoles in a **fan-out** manner.
- Keep pools, sport events, results, settlements, and related state aligned across totes so that the same pool can be offered and settled consistently (e.g. host creates pool → guests get the same pool; host settles → guests settle the same way).

## Roles

| Role | Who | What |
|------|-----|------|
| **Host** | The tote where the action originated (e.g. pool created, event settled). | Produces messages to the **local** commingling topic (console/CbToteLogic) and/or consumes local topic and republishes to **global** (CFS). |
| **Guest** | Other totes that participate in the same commingled setup. | Consume from the **global** commingling topic and apply the same actions on the local tote (CFS). |

A single CFS instance acts as **host** for its own tote (consumes **local**, publishes to **global**) and as **guest** for other totes (consumes **global**, applies to local DB).

## Message flow

- **Local commingling topic** (Kafka): Published by the **console** (e.g. CbToteLogic when a pool is created/updated, sport event changes, settlements). Consumed by **CFS on the host** to process and optionally upload payloads (e.g. S3) and publish to global.
- **Global commingling topic** (Kafka): Published by **CFS host** (one message per guest gateway when applicable). Consumed by **CFS on each guest** to replicate the action locally (create/update pool, apply result, settle, etc.).
- **Dispatcher** in CFS: **LocalMessage** → host services; **GlobalMessage** → guest (receiver) services.

## What gets replicated

- **Pools**: Create/update (via S3 JSON + PoolPublished), visibility, controller restart, abandonment, settlement, trading, closed, reopened.
- **Sport events**: Progress, abandoned, two-teams score, race data, reverse, update, score amendment, probability.
- **Markets / MVP / Fantasy**: Probability, abandonment, results, amendments, manual settlement, MVP withdrawal/reinstatement, runner updates.
- **Tickets**: Uploaded to S3 (optional); guests can use for cycle data / engine.

## Data stores

- **Tote DB** (per tote): Pools, legs, competitors, sport_events, markets, etc. **Commingled_*** tables hold the mapping from host entity id (`external_id`) to local entity id; `is_local` marks the host.
- **Commingling DB** (shared): Gateways, SharedPools, SharedPoolGateway, SharedPoolInfo — which pools are shared with which gateways and cross-tote metadata.
- **S3**: Pool JSON blobs (and optionally ticket files) produced by host, consumed by guests.

## Conventions

- **Entity mapping**: Host entity id → guest entity id is stored in tote DB tables **commingled_*** (e.g. `commingled_pools`, `commingled_competitors`). Column **external_id** = host entity id; local id is the row’s own id. If **external_id** equals the local entity id (or **is_local** is set), this tote is the host for that entity.
- **Gateway**: Each tote is identified by a gateway name (config); used for routing (which topic to publish to, which pool categories are allowed per gateway).

## Applications involved

- **Console / CbToteLogic**: Creates/updates pools and raises **PoolChangedLocalMessage** (and other local messages) to the local commingling topic when the pool is commingled.
- **Commingling Feed System (CFS)**: .NET 8 worker. Consumes **local** topic (host behaviour: process, S3, publish global) and **global** topic (guest behaviour: apply on local tote). Also runs pool settlement and pool closure loops. Codebase: `comminglingfeedsystem`.
- **Cycle data / Engine**: Use pool and ticket data (including from S3 for commingled tickets); pool start is triggered by cycle data finalising the pool (see pool-start-sequence.md). Engine does not implement commingling replication; it consumes the result (pools and tickets present on the tote).
