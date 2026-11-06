// Every current fact of one library, as the export renders it (#8). Params: $library.
// added   = the earliest business start among versions that were in force (a never-valid retraction has
//           valid_to = valid_from, so it never was) and not replaced by a correction: the same candidates as
//           fact_as_of. A correction that moved the start moves Added too.
// updated = when the current version was recorded, if it replaced an earlier one; for a first version, the legacy
//           **Updated** date kept by the ingest (else null).
MATCH (l:KbLibrary {name: $library})<-[:KB_PART_OF]-(c:KbCategory)<-[:KB_IN_CATEGORY]-(f:KbFact)
MATCH (f)-[:KB_HAS_VERSION]->(v:KbCurrent)
WITH c, f, v,
     [(f)-[:KB_HAS_VERSION]->(x:KbFactVersion)
      WHERE x.status IN ['active', 'superseded', 'retracted']
        AND NOT EXISTS { (:KbFactVersion {change_type: 'correction'})-[:KB_SUPERSEDES]->(x) }
        AND (x.valid_to IS NULL OR x.valid_to > x.valid_from) | x.valid_from] AS starts
RETURN f.id AS id, c.path AS category, v.version_id AS version_id, v.kind AS kind,
       v.title AS title, v.summary AS summary, v.statement AS statement, coalesce(v.keywords, []) AS keywords,
       v.context AS context,
       reduce(m = v.valid_from, s IN starts | CASE WHEN s < m THEN s ELSE m END) AS added,
       CASE v.change_type WHEN 'create' THEN v.legacy_updated ELSE v.recorded_at END AS updated
ORDER BY category, toLower(title), id;
