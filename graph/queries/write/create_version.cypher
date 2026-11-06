// A new version of fact $id. Params: $id, $vid, $props (version properties), $current (adds :KbCurrent),
// $author, $author_name. search_text is built here, with the same expression as the stale_search_text check.
MATCH (f:KbFact {id: $id})
MERGE (p:KbPerson {email: $author}) ON CREATE SET p.name = $author_name
CREATE (f)-[:KB_HAS_VERSION]->(v:KbFactVersion {version_id: $vid})-[:KB_AUTHORED_BY]->(p)
SET v += $props
SET v.search_text = toLower(v.title + '\n' + v.summary + '\n'
      + reduce(acc = '', k IN coalesce(v.keywords, []) | acc + CASE acc WHEN '' THEN '' ELSE ' ' END + k)
      + '\n' + v.statement)
FOREACH (_ IN CASE WHEN $current THEN [1] ELSE [] END | SET v:KbCurrent)
RETURN v.version_id AS version_id;
