<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Fantasy/Mido images and team keys

Pick'em uses sport_event_players.image_id; team S3 key format; FOOTBALL teams use the league subcode.

---

## Fantasy / Mido competitor images
**Added**: 2026-08-21
**Context**: Pool 2073 (Pick'em 10, `FANTASY_OU`) after BulkImageUploader Scenario 4 team-only upload
**Id**: `fantasy-mido-competitor-images`

Mido pick'em player cards use **`sport_event_players.image_id` → `images.file_url`**, returned as `legs[].player.image_url` from `GET /api/pools/:id`. If `sport_event_players.image_id` is null, the API sends `image_url: null` and the FE renders no `<img>`.

Updating these does **not** change pick'em player cards:
- `competitors.add_info_json.image_id` (master competitor / player row)
- `sport_event_competitors.add_info_json.image_id` (event team snapshot)

To make a new image show on a live pick'em pool, set `sport_event_players.image_id` for that pool’s player rows (and ensure the `images` row exists).

`images.file_name` is the S3 object key; `file_url` is the public URL for that key. The FE uses `file_url` from the API.

---

## FOOTBALL team `sport_sub_code`
**Added**: 2026-08-21
**Context**: Scenario 4 team-only lookup for Coventry / Hull / Ipswich
**Id**: `football-team-sport-sub-code`

FOOTBALL (and NBA/NFL/MLB/NHL) team competitors are **not** stored as `sport_sub_code = 'TEAMS'`. They use the league code (`GBFPREM`, `US_NBA`, …). Lookup team by `ext_id` + `ext_source_code = 'SportsData'` + `sport_code`, excluding `PLAYERS`.

---

## Team image S3 key (BB and normal pools)
**Added**: 2026-08-21
**Context**: Scenario 4 team-only; agreed format A for both BetBuilder and pools
**Id**: `team-image-s3-key-bb-and-normal-pools`

> Team images are stored at the S3 key {Sport}/{Season}/{Sport}_{GlobalTeamId}.{EXT}, e.g. FOOTBALL/2026/FOOTBALL_90002051.PNG.

Team objects use:

`{Sport}/{Season}/{Sport}_{GlobalTeamId}.{EXT}`

Example: `FOOTBALL/2026/FOOTBALL_90002051.PNG`

Source files: `{root}/{sport}/{season}/{global_team_id}.{ext}` where `global_team_id` is the team competitor `ext_id`.

BulkImageUploader Scenario 4 `team-only` writes S3 + `images` and can set `competitors` (team + players). It does **not** update `sport_event_players`.
