# Schema checks

`integrity.cypher` holds 25 checks. Each starts with a `// check: <name>` line, is one read-only query returning `(check, detail)`, and must return zero rows. `kb.py integrity` runs them all and exits non-zero on any row. It also runs inside every write, before commit, and before every export.

Constraints and indexes are not defined here. They are created by numbered scripts in [`../migrations/`](../migrations/), so every instance gets the same schema in the same order.

The rules are listed in the plan, under *Integrity*.
