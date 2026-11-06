// The current version of one fact, in full. Params: $id.
MATCH (f:KbFact {id: $id})-[:KB_HAS_VERSION]->(v:KbCurrent)
RETURN f.id AS id,
       head([(f)-[:KB_IN_CATEGORY]->(c:KbCategory) | c.path]) AS category,
       v {.version_id, .title, .summary, .statement, .keywords, .kind, .status, .change_type,
          .valid_from, .valid_to, .recorded_at, .recorded_to,
          .why, .context, .alternatives, .trade_offs, .revisit_if,
          .source_type, .source_refs, .confidence, .via,
          .retract_why, .retract_source_refs, .retracted_by, .approval_recorded_by, .approval_evidence} AS version,
       head([(v)-[:KB_AUTHORED_BY]->(p:KbPerson) | p.email]) AS author,
       [(v)-[:KB_APPROVED_BY]->(p:KbPerson) | p.email] AS approved_by;
