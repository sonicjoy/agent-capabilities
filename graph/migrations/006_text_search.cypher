// 006 — replace the full-text index with TEXT indexes. Idempotent.
// On Aura Professional the KB logins (built-in reader/publisher) can't execute procedures, so
// db.index.fulltext.queryNodes is Forbidden for them (checked on staging 2026-10-07) and kb_current_text is unusable.
// kb.py search instead matches lower-cased terms with plain Cypher CONTAINS on :KbCurrent; TEXT indexes serve
// CONTAINS / STARTS WITH on string properties. `keywords` is a list, so it is matched without an index.

DROP INDEX kb_current_text IF EXISTS;
CREATE TEXT INDEX kb_current_title IF NOT EXISTS FOR (n:KbCurrent) ON (n.title);
CREATE TEXT INDEX kb_current_summary IF NOT EXISTS FOR (n:KbCurrent) ON (n.summary);
CREATE TEXT INDEX kb_current_statement IF NOT EXISTS FOR (n:KbCurrent) ON (n.statement);
