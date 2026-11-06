// Lock a fact for the rest of the transaction and return its state. Params: $id.
// Writing f.updated_at takes the write lock, so a concurrent writer waits and then sees the new current version.
MATCH (f:KbFact {id: $id})
SET f.updated_at = datetime()
RETURN f.id AS id,
       head([(f)-[:KB_IN_CATEGORY]->(c:KbCategory) | c.path]) AS category,
       head([(f)-[:KB_HAS_VERSION]->(v:KbCurrent) |
             v {.version_id, .status, .change_type, .title, .summary, .statement, .keywords, .kind,
                .valid_from, .valid_to, .recorded_at, .recorded_to}]) AS current,
       head(COLLECT {
         MATCH (f)-[:KB_HAS_VERSION]->(r:KbFactVersion {status: 'retracted'})
         WHERE NOT EXISTS { (:KbFactVersion)-[:KB_SUPERSEDES]->(r) }
         RETURN r {.version_id, .status, .change_type, .title, .summary, .statement, .keywords, .kind,
                   .valid_from, .valid_to, .recorded_to}
       }) AS open_retraction;
