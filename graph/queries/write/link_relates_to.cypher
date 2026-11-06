// Fact -> fact link with a type. Params: $from, $to, $rel. Idempotent.
MATCH (a:KbFact {id: $from}), (b:KbFact {id: $to})
MERGE (a)-[r:KB_RELATES_TO {rel: $rel}]->(b)
RETURN count(r) AS linked;
