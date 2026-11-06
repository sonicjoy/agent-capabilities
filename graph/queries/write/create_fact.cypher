// A new fact identity in a leaf category. Params: $id, $category, $now. Uniqueness on KbFact.id stops duplicates.
MATCH (c:KbCategory {path: $category})
CREATE (f:KbFact {id: $id, created_at: $now, updated_at: $now})-[:KB_IN_CATEGORY]->(c)
RETURN f.id AS id;
