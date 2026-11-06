<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# MVP uses market_metrics, NOT market_results

**Added**: 2026-01-27
**Context**: Recorded during debug of MVP market_metrics never updated (pool 51177, markets 18432–18435).
**Id**: `mvp-uses-market-metrics`

For **FantasyMvp** (MVP) markets in cbtote, the application uses **`market_metrics`** as the source of truth for metric values, **not** `market_results`.

- **`market_metrics`**: holds per-player metric values (e.g. `metric_value`, `metric_id`, `sport_event_player_id`). For MVP, this is what the system reads and displays.
- **`market_results`**: not used for MVP (unlike some other fantasy market types that may use `market_results`).

When implementing or debugging MVP flows (e.g. stats_feed → CbToteLogic `SetResults` / `IMvpMarketResultService`), target **`market_metrics`** for persisting and reading live metric values.
