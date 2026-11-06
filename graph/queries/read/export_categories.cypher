// Every category of one library, for the export (#8). Params: $library.
MATCH (l:KbLibrary {name: $library})<-[:KB_PART_OF]-(c:KbCategory)
RETURN l.title AS library_title, l.description AS library_description,
       c.path AS path, c.title AS title, c.description AS description
ORDER BY path;
