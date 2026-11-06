// Remove a mistaken fact/component -> repo link. Params: $from, $from_kind ('fact' | 'component'), $to.
MATCH (x)-[r:KB_IMPLEMENTED_IN]->(:KbCodeRepo {path: $to})
WHERE ($from_kind = 'fact' AND x:KbFact AND x.id = $from)
   OR ($from_kind = 'component' AND x:KbSystemComponent AND x.name = $from)
DELETE r
RETURN count(*) AS unlinked;
