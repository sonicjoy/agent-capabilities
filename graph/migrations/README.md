# Migrations

These scripts set up and change the KB schema and seed data. [`graph/admin/migrate.py`](../admin/migrate.py) applies them as the instance admin. (The header of `001_constraints.cypher` still says `kb.py migrate`; it can't be edited because it's checksum-locked.)

- Name them `NNN_<name>.cypher` (`001_constraints.cypher`, `002_indexes.cypher`, …). They run in number order.
- Each script must be **idempotent** (`IF NOT EXISTS`, `MERGE`), so running it twice changes nothing.
- An applied script is recorded as `:KbMigration {id: 'NNN_<name>', checksum, applied_at}` and is skipped afterwards.
- Never edit a script once it has been applied anywhere: a changed checksum is an error. Add a new one instead.
- Statements are separated by `;` at the end of a line, and schema statements run one per transaction.
- Use only `Kb*` labels, `KB_*` relationship types and `kb_*` constraint and index names.
