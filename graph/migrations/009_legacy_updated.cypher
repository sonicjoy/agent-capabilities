// 009 — type for legacy_updated, the **Updated** date the one-off markdown ingest (#7) keeps. Idempotent.
CREATE CONSTRAINT kb_fv_legacy_updated_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.legacy_updated IS :: ZONED DATETIME;
