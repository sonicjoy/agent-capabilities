// Fact or component -> code repo. Params: $from, $from_kind ('fact' | 'component'), $to (repo path). Idempotent.
MATCH (r:KbCodeRepo {path: $to})
OPTIONAL MATCH (a:KbFact {id: $from}) WHERE $from_kind = 'fact'
OPTIONAL MATCH (s:KbSystemComponent {name: $from}) WHERE $from_kind = 'component'
WITH r, coalesce(a, s) AS x
WHERE x IS NOT NULL
MERGE (x)-[l:KB_IMPLEMENTED_IN]->(r)
RETURN count(l) AS linked;
