// Remove a mistaken fact -> fact link (links aren't versioned). Params: $from, $to, $rel.
MATCH (:KbFact {id: $from})-[r:KB_RELATES_TO {rel: $rel}]->(:KbFact {id: $to})
DELETE r
RETURN count(*) AS unlinked;
