// Current facts in a category and everything below it. Params: $path_prefix ('' = whole library), $limit.
// A prefix matches whole path segments: 'business/pool' does not match 'business/pools'.
MATCH (c:KbCategory)
WHERE $path_prefix = '' OR c.path = $path_prefix OR c.path STARTS WITH $path_prefix + '/'
MATCH (f:KbFact)-[:KB_IN_CATEGORY]->(c)
MATCH (f)-[:KB_HAS_VERSION]->(v:KbCurrent)
RETURN f.id AS id, v.title AS title, v.summary AS summary, v.kind AS kind, c.path AS category
ORDER BY category, title
LIMIT $limit;
