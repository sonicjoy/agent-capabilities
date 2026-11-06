<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# cbtote Knowledge Index

cbtote data model and domain rules.

**Last Updated**: 2026-08-21

## Files in This Directory
| File | Title | Added | Updated | Description |
|------|-------|-------|---------|-------------|
| [competitor-images.md](competitor-images.md) | Fantasy/Mido images and team keys | 2026-08-21 | - | Pick'em uses sport_event_players.image_id; team S3 key format; FOOTBALL teams use the league subcode. |
| [mvp-uses-market-metrics.md](mvp-uses-market-metrics.md) | MVP uses market_metrics | 2026-01-27 | - | FantasyMvp reads and writes market_metrics; market_results is not used. |
| [mvp-withdrawal-remaining-units.md](mvp-withdrawal-remaining-units.md) | MVP withdrawal and favourite for remaining units | 2026-02-11 | - | Withdrawn/favourite from market_snapshot, with a fallback to sport_event_competitors. |

## Quick Reference
- pick'em / pick'em images: competitor-images.md - Mido pick'em player cards use sport_event_players.image_id → images.file_url, returned as legs[].player.image_url from GET /api/pools/:id.
- FOOTBALL teams: competitor-images.md - FOOTBALL (and NBA/NFL/MLB/NHL) team competitors are not stored as sport_sub_code = 'TEAMS'.
- team images / team S3 key: competitor-images.md - Team images are stored at the S3 key {Sport}/{Season}/{Sport}_{GlobalTeamId}.{EXT}, e.g. FOOTBALL/2026/FOOTBALL_90002051.PNG.
- MVP / market_metrics / MVP uses market_metrics: mvp-uses-market-metrics.md - For FantasyMvp (MVP) markets in cbtote, the application uses market_metrics as the source of truth for metric values, not market_results.
- MVP withdrawal: mvp-withdrawal-remaining-units.md - For FANTASY_MVP pools, favourite and withdrawn bins are used to redirect units (e.g. tickets on a withdrawn selection go to the favourite).

## Parent
- [../index.md](../index.md)
