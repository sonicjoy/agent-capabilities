# Write templates

These are the parameterised write queries behind `kb.py write …` (#6). Each command is one transaction that checks integrity before it commits.

`skills/knowledge/scripts/kbwrite.py` runs these in one transaction per command:

| Template | Step |
|----------|------|
| `lock_fact` | Lock the fact (`SET f.updated_at`) and return its category, current version and open retraction |
| `category_info` | Category exists? Leaf? How many facts? |
| `create_fact`, `create_version` | New fact identity; new version (builds `search_text` in Cypher, adds `:KbCurrent` unless draft) |
| `supersede` | Link the new version to the old one and close the old one |
| `find_predecessor`, `set_valid_to` | A correction that moves `valid_from` moves the previous rule's `valid_to` |
| `retract`, `draft_info`, `person_info`, `promote` | Retraction; draft promotion with `KB_APPROVED_BY` (`person_info`: is `--confirmed-by` already in the KB?) |
| `move_category` | Re-point `KB_IN_CATEGORY` (the only relationship delete) |
| `create_category`, `link_*`, `unlink_*`, `source_kinds`, `upsert_component`, `upsert_repo` | Taxonomy and architecture links |

- Every command starts by locking the fact, then checks that `--expected-current` is still its latest version.
- **Datetimes passed to templates are always offset UTC** (`datetime.timezone.utc`). Neo4j returns DateTimes with a named `UTC` zone, and Cypher doesn't treat those as equal to the same instant with `+00:00`; `kbwrite._native` converts everything it reads back. New templates must not mix the two.
- Relationship deletes exist only in `move_category` and `unlink_*`; no template deletes a node.
- Never delete nodes, and never edit a version's content in place: write a new version and move `:KbCurrent`.
- Use parameters only. No other Cypher writes to the KB.
