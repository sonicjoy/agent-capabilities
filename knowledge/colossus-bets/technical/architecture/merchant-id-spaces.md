<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Tote vs wallet merchant IDs (BB / Fantasy)

**Added**: 2026-08-18
**Context**: BB entries sit under tote `merchant_id` 255 (Fantasy); matching wallet `merchant_transaction_details` rows use `merchant_id` 1 (`fantasyprod`). Confirmed this is source data, not a DW ETL remapping.
**Id**: `tote-vs-wallet-merchant-ids-bb-fantasy`

Tote/`bb_tote` `merchants` are **brands**. Wallet (`cb-wallet`) `merchants` are **client systems of the wallet service**. The two `id` sequences are independent and must never be joined or equated. Tote `1 = Colossus Bets` and wallet `1 = fantasyprod` is coincidence.

| System | Table | Meaning | Live Fantasy row |
|--------|--------|---------|------------------|
| `cbtote` / `bb_tote` | `merchants` | Brand the customer belongs to | `255` = Fantasy (USD, region `fantasy`) |
| `cb-wallet` | `merchants` | Integration that posted the txn | `1` = fantasyprod (`2` = Dataflow). There is no 255. |

`bb_tote.entries` has no `merchant_id`; brand comes from `bb_tote.customers.merchant_id` (all live BB entries are 255). Wallet MTD `merchant_id` is whoever authenticated to the wallet (fantasyprod → 1).

**Link BB money to an entry**: `bb_tote.entries.merchant_ref` = `cb-wallet.merchant_transaction_details.merchant_bet` (e.g. `1002-4742`). Do not use `ticket_id` (always null for BB). One entry can have several MTD/txn rows (`BB_BET`, `BB_PAYOUT`, `BB_VOID`). DW copies `merchant_id` verbatim.

**Resolve brand for reports**: through the customer (`wallet.users.customer_id` → `data.customers_list.merchant_id` → `tote.merchants.name`), not through MTD `merchant_id`.

**Invariant (prod 2026-08-18)**: every BB entry has a non-empty `merchant_ref` and at least one matching MTD row. Treat as a product rule to monitor, not something the DW invents.
