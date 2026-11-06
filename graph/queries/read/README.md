# Read templates

These are the allowlisted read queries. `kb.py read <name>` loads `<name>.cypher` from here and binds its parameters (#5). Agents don't run other Cypher against the KB.

| Template | Used by |
|----------|---------|
| `current_by_category` | `kb.py read current-by-category` |
| `search` | `kb.py read search` (kb.py prepares `$terms`) |
| `fact` / `fact_as_of` / `fact_kb_as_of` | `kb.py read fact` (current / business time / record time) |
| `related` | `kb.py read related` |
| `history` | `kb.py read history` |

- One statement per file. Use parameters (`$id`, `$terms`, `$limit`, `$at`), never string formatting.
- "Current" means the `:KbCurrent` label.
- Return compact rows (`id`, `title`, `summary`) unless the template is meant to return a full fact.
