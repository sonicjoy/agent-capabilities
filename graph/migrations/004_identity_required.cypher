// 004 — identity keys must be present and strings. Uniqueness (001) does not imply NOT NULL, so a node without its key
// could commit and break integrity details and the category prefix match. Idempotent.

CREATE CONSTRAINT kb_library_name_required IF NOT EXISTS FOR (n:KbLibrary) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT kb_library_name_type IF NOT EXISTS FOR (n:KbLibrary) REQUIRE n.name IS :: STRING;
CREATE CONSTRAINT kb_category_path_required IF NOT EXISTS FOR (n:KbCategory) REQUIRE n.path IS NOT NULL;
CREATE CONSTRAINT kb_category_path_type IF NOT EXISTS FOR (n:KbCategory) REQUIRE n.path IS :: STRING;
CREATE CONSTRAINT kb_fact_id_required IF NOT EXISTS FOR (n:KbFact) REQUIRE n.id IS NOT NULL;
CREATE CONSTRAINT kb_fact_id_type IF NOT EXISTS FOR (n:KbFact) REQUIRE n.id IS :: STRING;
CREATE CONSTRAINT kb_fv_version_id_required IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.version_id IS NOT NULL;
CREATE CONSTRAINT kb_fv_version_id_type IF NOT EXISTS FOR (n:KbFactVersion) REQUIRE n.version_id IS :: STRING;
CREATE CONSTRAINT kb_person_email_required IF NOT EXISTS FOR (n:KbPerson) REQUIRE n.email IS NOT NULL;
CREATE CONSTRAINT kb_person_email_type IF NOT EXISTS FOR (n:KbPerson) REQUIRE n.email IS :: STRING;
CREATE CONSTRAINT kb_system_component_name_required IF NOT EXISTS FOR (n:KbSystemComponent) REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT kb_code_repo_path_required IF NOT EXISTS FOR (n:KbCodeRepo) REQUIRE n.path IS NOT NULL;
CREATE CONSTRAINT kb_migration_id_required IF NOT EXISTS FOR (n:KbMigration) REQUIRE n.id IS NOT NULL;
CREATE CONSTRAINT kb_migration_checksum_required IF NOT EXISTS FOR (n:KbMigration) REQUIRE n.checksum IS NOT NULL;
