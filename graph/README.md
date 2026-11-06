# Colossus KB graph

The Colossus Bets knowledge base is stored in Neo4j Aura. This folder holds everything that defines the graph. Agents and humans reach it only through `kb.py` (`skills/knowledge/scripts/`). The design is in [`docs/plans/colossus-knowledge-base.md`](../docs/plans/colossus-knowledge-base.md).

| Folder | Holds | Work item |
|--------|-------|-----------|
| [`schema/`](schema/) | `integrity.cypher`, the checks that must return zero rows | #3 |
| [`migrations/`](migrations/) | Numbered, idempotent schema and seed scripts | #3 |
| [`queries/read/`](queries/read/) | Allowlisted read templates | #5 |
| [`queries/write/`](queries/write/) | Parameterised write templates | #6 |
| [`admin/`](admin/) | One-off admin scripts (production users and roles) | #15 |

## Model in brief

- `KbFact` is an identity that never changes. Each `KbFactVersion` holds the content and is never edited. The current version also carries the label `:KbCurrent`, which is the only definition of "current".
- Two timelines: `valid_from`/`valid_to` (when the rule applied in the business) and `recorded_at`/`recorded_to` (when the KB said it). `change_type` separates a **change** from a **correction**.
- Nothing is deleted. A retracted fact keeps its history.

## Naming

Production shares its database with other graphs, so every KB name has a prefix, on every instance:

| Kind | Rule | Example |
|------|------|---------|
| Labels | `Kb` + name | `KbFact`, `KbFactVersion`, `KbCurrent` |
| Relationship types | `KB_` + name | `KB_HAS_VERSION`, `KB_SUPERSEDES` |
| Constraints and indexes | `kb_` prefix | `kb_fact_id`, `kb_current_search_text` |

Templates and integrity checks match only these names.

## Environments

| | Staging | Production |
|---|---------|------------|
| Instance | Aura Professional `839b9d82` (KB only) | Aura Professional `fc801360` (shared) |
| Database | `neo4j` | `neo4j` |
| `kb.py` login | `kb_writer` | `kb_writer` |
| Agent login | `kb_reader` | `kb_reader` |

Connection settings come from `COLOSSUS_KB_URI`, `COLOSSUS_KB_USER`, `COLOSSUS_KB_PASSWORD` and `COLOSSUS_KB_DATABASE`. Credentials are never committed.
