// Every version of a fact, oldest first, including drafts and retractions. Params: $id.
MATCH (f:KbFact {id: $id})-[:KB_HAS_VERSION]->(v:KbFactVersion)
RETURN v.version_id AS version_id, v.status AS status, v.change_type AS change_type, v:KbCurrent AS current,
       v.title AS title, v.summary AS summary, v.why AS why, v.source_refs AS source_refs,
       v.valid_from AS valid_from, v.valid_to AS valid_to, v.recorded_at AS recorded_at, v.recorded_to AS recorded_to,
       v.retract_why AS retract_why, v.retract_source_refs AS retract_source_refs, v.retracted_by AS retracted_by,
       head([(v)-[:KB_SUPERSEDES]->(o:KbFactVersion) | o.version_id]) AS supersedes,
       head([(v)-[:KB_AUTHORED_BY]->(p:KbPerson) | p.email]) AS author,
       [(v)-[:KB_APPROVED_BY]->(p:KbPerson) | p.email] AS approved_by,
       v.approval_recorded_by AS approval_recorded_by, v.approval_evidence AS approval_evidence
ORDER BY v.recorded_at, v.version_id;
