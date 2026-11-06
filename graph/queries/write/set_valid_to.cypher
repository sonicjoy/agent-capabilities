// Move a closed version's business end date (a correction moved its successor's start). Params: $vid, $valid_to.
MATCH (v:KbFactVersion {version_id: $vid})
SET v.valid_to = $valid_to
RETURN v.version_id AS version_id;
