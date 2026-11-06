// 008 — types for the draft base and retraction audit properties written by kb.py (#6). Idempotent.
// base_version_id: the version a draft was written against (promote refuses if the fact moved on).
// retract_*: why, sources and who, set on the retracted version.

CREATE CONSTRAINT kb_fv_base_version_id_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.base_version_id IS :: STRING;
CREATE CONSTRAINT kb_fv_retract_why_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.retract_why IS :: STRING;
CREATE CONSTRAINT kb_fv_retract_source_refs_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.retract_source_refs IS :: LIST<STRING NOT NULL>;
CREATE CONSTRAINT kb_fv_retracted_by_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.retracted_by IS :: STRING;
