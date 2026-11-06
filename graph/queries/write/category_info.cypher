// Whether a category exists, whether it is a leaf, and how many facts it holds. Params: $path.
MATCH (c:KbCategory {path: $path})
RETURN c.path AS path,
       EXISTS { MATCH (x:KbCategory) WHERE x.path STARTS WITH c.path + '/' } AS has_children,
       COUNT { (:KbFact)-[:KB_IN_CATEGORY]->(c) } AS facts;
