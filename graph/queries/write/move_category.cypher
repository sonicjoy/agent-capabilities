// Re-point a fact to another (leaf) category; the move is recorded by the new version written with it.
// Params: $id, $category. The only relationship delete in the KB templates.
MATCH (f:KbFact {id: $id})-[r:KB_IN_CATEGORY]->(:KbCategory)
DELETE r
WITH DISTINCT f
MATCH (c:KbCategory {path: $category})
CREATE (f)-[:KB_IN_CATEGORY]->(c)
RETURN f.id AS id;
