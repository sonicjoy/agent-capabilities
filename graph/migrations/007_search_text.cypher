// 007 — one case-insensitive search field instead of per-field TEXT indexes. Idempotent.
// Search must ignore case, and an index on v.title can't serve toLower(v.title) CONTAINS $t, so the 006 indexes would
// never be used. kb.py now writes `search_text` on every version:
//   toLower(title + '\n' + summary + '\n' + keywords joined by ' ' + '\n' + statement)
// and search matches `v.search_text CONTAINS $term` on :KbCurrent, served by kb_current_search_text.
// The integrity check `stale_search_text` keeps it in line with the fields it is built from.

DROP INDEX kb_current_title IF EXISTS;
DROP INDEX kb_current_summary IF EXISTS;
DROP INDEX kb_current_statement IF EXISTS;
CREATE CONSTRAINT kb_fv_search_text_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.search_text IS NOT NULL;
CREATE CONSTRAINT kb_fv_search_text_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.search_text IS :: STRING;
CREATE TEXT INDEX kb_current_search_text IF NOT EXISTS FOR (n:KbCurrent) ON (n.search_text);
