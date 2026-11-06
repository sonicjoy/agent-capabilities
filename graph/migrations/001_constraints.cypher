// 001 — identity, required properties and property types for the Colossus KB.
// Idempotent. Applied by `kb.py migrate` as the instance admin.
// Rules the database can't express (enums, one :KbCurrent per fact, non-empty lists) live in graph/schema/integrity.cypher.

// ---- identity
CREATE CONSTRAINT kb_library_name IF NOT EXISTS FOR (n:KbLibrary) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT kb_category_path IF NOT EXISTS FOR (n:KbCategory) REQUIRE n.path IS UNIQUE;
CREATE CONSTRAINT kb_fact_id IF NOT EXISTS FOR (n:KbFact) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT kb_fact_version_id IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.version_id IS UNIQUE;
CREATE CONSTRAINT kb_system_component_name IF NOT EXISTS FOR (n:KbSystemComponent) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT kb_code_repo_path IF NOT EXISTS FOR (n:KbCodeRepo) REQUIRE n.path IS UNIQUE;
CREATE CONSTRAINT kb_person_email IF NOT EXISTS FOR (n:KbPerson) REQUIRE n.email IS UNIQUE;
CREATE CONSTRAINT kb_migration_id IF NOT EXISTS FOR (n:KbMigration) REQUIRE n.id IS UNIQUE;

// ---- KbCategory
CREATE CONSTRAINT kb_category_title_required IF NOT EXISTS FOR (n:KbCategory) REQUIRE n.title IS NOT NULL;
CREATE CONSTRAINT kb_category_title_type IF NOT EXISTS FOR (n:KbCategory) REQUIRE n.title IS :: STRING;

// ---- KbFact
CREATE CONSTRAINT kb_fact_created_at_required IF NOT EXISTS FOR (n:KbFact) REQUIRE n.created_at IS NOT NULL;
CREATE CONSTRAINT kb_fact_created_at_type IF NOT EXISTS FOR (n:KbFact) REQUIRE n.created_at IS :: ZONED DATETIME;
CREATE CONSTRAINT kb_fact_updated_at_type IF NOT EXISTS FOR (n:KbFact) REQUIRE n.updated_at IS :: ZONED DATETIME;

// ---- KbFactVersion: required strings
CREATE CONSTRAINT kb_fv_title_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.title IS NOT NULL;
CREATE CONSTRAINT kb_fv_title_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.title IS :: STRING;
CREATE CONSTRAINT kb_fv_summary_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.summary IS NOT NULL;
CREATE CONSTRAINT kb_fv_summary_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.summary IS :: STRING;
CREATE CONSTRAINT kb_fv_statement_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.statement IS NOT NULL;
CREATE CONSTRAINT kb_fv_statement_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.statement IS :: STRING;
CREATE CONSTRAINT kb_fv_kind_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.kind IS NOT NULL;
CREATE CONSTRAINT kb_fv_kind_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.kind IS :: STRING;
CREATE CONSTRAINT kb_fv_status_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.status IS NOT NULL;
CREATE CONSTRAINT kb_fv_status_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.status IS :: STRING;
CREATE CONSTRAINT kb_fv_change_type_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.change_type IS NOT NULL;
CREATE CONSTRAINT kb_fv_change_type_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.change_type IS :: STRING;
CREATE CONSTRAINT kb_fv_source_type_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.source_type IS NOT NULL;
CREATE CONSTRAINT kb_fv_source_type_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.source_type IS :: STRING;
CREATE CONSTRAINT kb_fv_confidence_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.confidence IS NOT NULL;
CREATE CONSTRAINT kb_fv_confidence_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.confidence IS :: STRING;
CREATE CONSTRAINT kb_fv_via_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.via IS NOT NULL;
CREATE CONSTRAINT kb_fv_via_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.via IS :: STRING;

// ---- KbFactVersion: lists
CREATE CONSTRAINT kb_fv_source_refs_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.source_refs IS NOT NULL;
CREATE CONSTRAINT kb_fv_source_refs_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.source_refs IS :: LIST<STRING NOT NULL>;
CREATE CONSTRAINT kb_fv_keywords_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.keywords IS :: LIST<STRING NOT NULL>;

// ---- KbFactVersion: two timelines
CREATE CONSTRAINT kb_fv_valid_from_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.valid_from IS NOT NULL;
CREATE CONSTRAINT kb_fv_valid_from_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.valid_from IS :: ZONED DATETIME;
CREATE CONSTRAINT kb_fv_valid_to_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.valid_to IS :: ZONED DATETIME;
CREATE CONSTRAINT kb_fv_recorded_at_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.recorded_at IS NOT NULL;
CREATE CONSTRAINT kb_fv_recorded_at_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.recorded_at IS :: ZONED DATETIME;
CREATE CONSTRAINT kb_fv_recorded_to_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.recorded_to IS :: ZONED DATETIME;
