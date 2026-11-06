// New version $new replaces $old. Params: $new, $old, $old_status, $old_valid_to, $old_recorded_to.
// kb.py computes the old version's closing values (change: valid_to = new valid_from; correction: valid_* kept;
// re-activating a retracted fact: the retraction is left as it is).
MATCH (n:KbFactVersion {version_id: $new}), (o:KbFactVersion {version_id: $old})
CREATE (n)-[:KB_SUPERSEDES]->(o)
SET o.status = $old_status, o.valid_to = $old_valid_to, o.recorded_to = $old_recorded_to
REMOVE o:KbCurrent
RETURN o.version_id AS version_id;
