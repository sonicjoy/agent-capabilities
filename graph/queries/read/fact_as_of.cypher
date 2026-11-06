// What the rule was on a date (business time), by today's knowledge. Params: $id, $at (a time-zone-aware datetime from kb.py).
// Candidates are versions that were in force (active, superseded or retracted, never drafts) and were not replaced by
// a correction: a corrected version was wrong, and its correction carries the same business dates instead.
MATCH (f:KbFact {id: $id})-[:KB_HAS_VERSION]->(v:KbFactVersion)
WHERE v.status IN ['active', 'superseded', 'retracted']
  AND NOT EXISTS { (:KbFactVersion {change_type: 'correction'})-[:KB_SUPERSEDES]->(v) }
  AND v.valid_from <= $at AND (v.valid_to IS NULL OR $at < v.valid_to)
RETURN f.id AS id,
       head([(f)-[:KB_IN_CATEGORY]->(c:KbCategory) | c.path]) AS category,
       v {.version_id, .title, .summary, .statement, .keywords, .kind, .status, .change_type,
          .valid_from, .valid_to, .recorded_at, .recorded_to,
          .why, .context, .alternatives, .trade_offs, .revisit_if,
          .source_type, .source_refs, .confidence, .via,
          .retract_why, .retract_source_refs, .retracted_by, .approval_recorded_by, .approval_evidence} AS version,
       head([(v)-[:KB_AUTHORED_BY]->(p:KbPerson) | p.email]) AS author,
       [(v)-[:KB_APPROVED_BY]->(p:KbPerson) | p.email] AS approved_by
ORDER BY v.valid_from DESC, v.recorded_at DESC
LIMIT 1;
