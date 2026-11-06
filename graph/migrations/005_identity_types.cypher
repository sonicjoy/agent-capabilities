// 005 — string types for the identity keys 004 made required but left untyped. With this, every identity key is
// present and a STRING. Idempotent.

CREATE CONSTRAINT kb_system_component_name_type IF NOT EXISTS FOR (n:KbSystemComponent) REQUIRE n.name IS :: STRING;
CREATE CONSTRAINT kb_code_repo_path_type IF NOT EXISTS FOR (n:KbCodeRepo) REQUIRE n.path IS :: STRING;
CREATE CONSTRAINT kb_migration_id_type IF NOT EXISTS FOR (n:KbMigration) REQUIRE n.id IS :: STRING;
CREATE CONSTRAINT kb_migration_checksum_type IF NOT EXISTS FOR (n:KbMigration) REQUIRE n.checksum IS :: STRING;
