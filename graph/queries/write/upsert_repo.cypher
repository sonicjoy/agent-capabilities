// Create or update a code repo. Params: $path (e.g. colossus/cbtote), $web_url (null keeps the current value).
MERGE (r:KbCodeRepo {path: $path})
SET r.web_url = coalesce($web_url, r.web_url)
RETURN r.path AS path;
