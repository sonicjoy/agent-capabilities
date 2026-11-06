// The category tree: every category with whether it's a leaf (facts attach only to leaves) and its current facts.
// Params: $library.
MATCH (:KbLibrary {name: $library})<-[:KB_PART_OF]-(c:KbCategory)
RETURN c.path AS path, c.title AS title, c.description AS description,
       NOT EXISTS { MATCH (:KbLibrary {name: $library})<-[:KB_PART_OF]-(d:KbCategory) WHERE d.path STARTS WITH c.path + '/' }
         AS leaf,
       COUNT { (c)<-[:KB_IN_CATEGORY]-(:KbFact)-[:KB_HAS_VERSION]->(:KbCurrent) } AS facts
ORDER BY path;
