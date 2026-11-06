// The version in force just before $old (business time): its valid_to equals $old_valid_from, and it wasn't replaced
// by a correction. Used when a correction moves valid_from. Params: $id, $old, $old_valid_from.
MATCH (f:KbFact {id: $id})-[:KB_HAS_VERSION]->(pp:KbFactVersion)
WHERE pp.version_id <> $old AND pp.valid_to = $old_valid_from AND pp.status IN ['superseded', 'retracted']
  AND NOT EXISTS { (:KbFactVersion {change_type: 'correction'})-[:KB_SUPERSEDES]->(pp) }
RETURN pp.version_id AS version_id, pp.valid_from AS valid_from;
