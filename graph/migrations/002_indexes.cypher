// 002 — lookup and search indexes for the Colossus KB. Idempotent.

CREATE RANGE INDEX kb_fv_status IF NOT EXISTS FOR (n:KbFactVersion) ON (n.status);
CREATE RANGE INDEX kb_fv_kind IF NOT EXISTS FOR (n:KbFactVersion) ON (n.kind);
CREATE RANGE INDEX kb_fv_valid_from IF NOT EXISTS FOR (n:KbFactVersion) ON (n.valid_from);
CREATE RANGE INDEX kb_fv_recorded_at IF NOT EXISTS FOR (n:KbFactVersion) ON (n.recorded_at);

// Full-text search over current versions only: removing :KbCurrent on supersede or retract takes a version out of
// the index, so old versions never crowd current ones out of a small result limit. The English analyzer stems,
// so "settlement" also finds "settle". `keywords` is a string list.
CREATE FULLTEXT INDEX kb_current_text IF NOT EXISTS
FOR (n:KbCurrent) ON EACH [n.title, n.summary, n.keywords, n.statement]
OPTIONS { indexConfig: { `fulltext.analyzer`: 'english' } };
