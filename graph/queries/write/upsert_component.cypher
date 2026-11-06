// Create or update a system component. Params: $name, $kind, $description (null keeps the current value).
MERGE (s:KbSystemComponent {name: $name})
SET s.kind = coalesce($kind, s.kind), s.description = coalesce($description, s.description)
RETURN s.name AS name;
