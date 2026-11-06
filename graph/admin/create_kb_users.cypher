// Colossus KB service users, for staging (839b9d82) and production (fc801360), both database `neo4j`.
// Run once per instance as the instance admin (`neo4j`) in Aura Query / Neo4j Browser, after the first `graph/admin/migrate.py` run.
// Use different passwords per instance.
//
// Aura Professional lets the admin create users and assign roles, but not create roles or grant privileges
// (CREATE ROLE / GRANT / SHOW ROLE PRIVILEGES are Forbidden; checked on staging 2026-10-07). So the users get
// Neo4j's built-in roles:
//
// kb_reader -> reader    : agent MCP (neo4j-colossus-kb). The database refuses every write.
// kb_writer -> publisher : kb.py. Can write. On production it could also write the other graphs; only kb.py's
//                          templates (Kb*/KB_* only) keep it to the KB.
// Schema migrations (constraints, indexes) keep running as `neo4j`.
//
// Passwords are parameters: set them in the same session, never commit them, store them in the secret store.
//   :param readerPassword => '<from secret store>'
//   :param writerPassword => '<from secret store>'

CREATE USER kb_reader IF NOT EXISTS SET PASSWORD $readerPassword CHANGE NOT REQUIRED;
CREATE USER kb_writer IF NOT EXISTS SET PASSWORD $writerPassword CHANGE NOT REQUIRED;
GRANT ROLE reader TO kb_reader;
GRANT ROLE publisher TO kb_writer;

// Verify
SHOW USERS YIELD user, roles WHERE user STARTS WITH 'kb_' RETURN user, roles;
