<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# MVP withdrawal and favourite for remaining units

**Added**: 2026-02-11
**Context**: Withdrawing Drake Maye from fixture 409547 did not remove/redirect units.
**Id**: `mvp-withdrawal-favourite-ru`

For **FANTASY_MVP** pools, favourite and withdrawn bins are used to redirect units (e.g. tickets on a withdrawn selection go to the favourite). They are normally read from the event’s **market_histories** → **market_snapshot** (per leg’s market): `market_player_order` = bin, `withdrawn`, `pool_favourite`.

If the withdrawal/favourite event has **no market_histories** or **empty market_snapshot** (e.g. event written without snapshot), the engine would previously get no withdrawn bins, so units were not redirected.

**Fallback**: In `MarketBasedPoolEventFlowStrategy.ComputeFavouriteAndWithdrawnBins`, when `market_snapshot` is missing or empty for an MVP pool, we derive **withdrawn** and **favourite** from the current **sport event competitors** (from DB): for each leg selection, if the competitor (`sport_event_competitor_id`) has `withdrawn == true`, that selection’s bin is added to withdrawn bins; if a competitor has `favourite == true`, that bin is used as favourite. So even when the event payload has no snapshot, withdrawing a player (e.g. Drake Maye) in the fixture still updates remaining units once the competitor row is marked withdrawn.

**Implementation**: `MarketBasedPoolEventFlowStrategy.ComputeFavouriteAndWithdrawnBins` — prefer market_snapshot when present; otherwise use `spEvent.sport_event_competitors` and `leg.selections` to compute withdrawn bins and favourite bin.
