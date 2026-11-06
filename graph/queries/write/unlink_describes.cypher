// Remove a mistaken fact -> component link. Params: $from (fact id), $to (component name).
MATCH (:KbFact {id: $from})-[r:KB_DESCRIBES]->(:KbSystemComponent {name: $to})
DELETE r
RETURN count(*) AS unlinked;
