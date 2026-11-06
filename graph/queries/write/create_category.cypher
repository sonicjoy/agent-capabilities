// A new category in the colossus-bets library. Params: $path, $title, $description.
MATCH (l:KbLibrary {name: 'colossus-bets'})
CREATE (c:KbCategory {path: $path, title: $title, description: $description})-[:KB_PART_OF]->(l)
RETURN c.path AS path;
