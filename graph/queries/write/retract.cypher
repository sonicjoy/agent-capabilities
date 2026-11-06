// Retract the current version. Params: $vid, $now, $valid_to ($now, or its own valid_from for --never-valid),
// $why, $source_refs, $author.
MATCH (v:KbCurrent {version_id: $vid})
SET v.status = 'retracted', v.recorded_to = $now, v.valid_to = $valid_to,
    v.retract_why = $why, v.retract_source_refs = $source_refs, v.retracted_by = $author
REMOVE v:KbCurrent
RETURN v.version_id AS version_id;
