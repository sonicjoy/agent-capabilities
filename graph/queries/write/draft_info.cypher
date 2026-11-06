// A draft version, its fact, category and author. Params: $vid.
MATCH (f:KbFact)-[:KB_HAS_VERSION]->(d:KbFactVersion {version_id: $vid})
RETURN f.id AS id, d.status AS status, d.change_type AS change_type, d.valid_from AS valid_from,
       d.base_version_id AS base_version_id,
       head([(f)-[:KB_IN_CATEGORY]->(c:KbCategory) | c.path]) AS category,
       head([(d)-[:KB_AUTHORED_BY]->(p:KbPerson) | p.email]) AS author;
