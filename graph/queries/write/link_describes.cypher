// Fact -> system component. Params: $from (fact id), $to (component name). Idempotent.
MATCH (a:KbFact {id: $from}), (s:KbSystemComponent {name: $to})
MERGE (a)-[r:KB_DESCRIBES]->(s)
RETURN count(r) AS linked;
