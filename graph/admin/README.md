# Admin scripts

| Script | Where | When |
|--------|-------|------|
| `migrate.py` | Staging and production | Whenever `graph/migrations/` has new files. `--dry-run` first; production also needs `--yes` |
| `dump.py` | The source instance (read-only, `kb_reader`) | Migration (#15) and rehearsals: writes every KB node and relationship to JSON lines |
| `load.py` | The target instance, as its admin | Migration (#15): loads a dump in one verified transaction; production needs `--yes` |
| `kb_users.py` | Staging and production, as the admin | `add` / `remove` a person's logins, `set-password` (a person or one login), `create` the shared logins (hidden password prompts), `suspend-writer` / `activate-writer` (the migration freeze), `show` |
| `create_kb_users.cypher` | Staging (`839b9d82`) and production (`fc801360`), database `neo4j` on both | Once per instance, after its first migration run: staging in #3, production in #15 |

`create_kb_users.cypher` creates two users with Neo4j's built-in roles: `kb_reader` → `reader` (for the agent MCP; the database refuses its writes) and `kb_writer` → `publisher` (for `kb.py`). Aura Professional doesn't allow custom roles, so these can't be limited to KB labels.

### Per-person logins (#20)

Each person gets their own pair, so passwords aren't shared and a leaver can be cut off alone:

```
uv run graph/admin/kb_users.py add alberto manuel --yes     # kb_alberto (publisher) + kb_alberto_reader (reader), ...
uv run graph/admin/kb_users.py remove alberto --yes        # drops both logins; what they recorded stays
uv run graph/admin/kb_users.py set-password alberto --yes  # new passwords for both of alberto's logins
uv run graph/admin/kb_users.py set-password kb_alberto_reader --yes   # or for one login
uv run graph/admin/kb_users.py show
```

- You type each password at a `*` prompt; all prompts come before any change. Hand each person their two passwords through the team secret store, then they run `python scripts/setup_kb.py` with their own login names.
- `add` skips logins that already exist and keeps their password.
- Names are first names in lower case (`[a-z][a-z0-9]+`), not `reader` or `writer`. Two people with the same first name get a digit (`alberto2`), not a surname.
- `add` grants each login its role every time, so re-running it repairs a run that stopped half-way. `show` warns about any `kb_` login without a `reader` or `publisher` role.
- Remove a leaver rather than suspending them: suspension is reserved for the freeze, which suspends **every** `kb_` login with `publisher` and `activate-writer` reactivates every suspended one.

**Rollout, last step: retire the shared logins.** Until they are dropped, anyone with the old shared passwords can still write, which defeats per-person logins. Once **every** person's `kb.py status` shows their own login (`kb_<name>_reader@fc801360…`):

```
uv run graph/admin/kb_users.py remove-shared --yes     # production only; refuses until a per-person writer exists
```

Staging keeps `kb_reader` / `kb_writer` for the integration tests. People who still have the shared logins saved get asked for their own on their next `setup_kb.py` run.

To run it, log in to Aura Query or Neo4j Browser as the admin and set the passwords first:

```
:param readerPassword => '<from secret store>'
:param writerPassword => '<from secret store>'
```

Each instance gets its own passwords. Store them in the secret store, never in this repo.

## migrate.py

`migrate.py` applies `graph/migrations/NNN_*.cypher` as the instance admin and records each one with a checksum. It refuses to run if an applied migration was edited, or if the database has one this checkout doesn't. It targets `COLOSSUS_KB_URI` / `COLOSSUS_KB_DATABASE`, the same settings `kb.py` uses.

The admin login is read **only from the current terminal session** (`COLOSSUS_KB_ADMIN_USER`, `COLOSSUS_KB_ADMIN_PASSWORD`), never from user-level variables or a config file. That way the admin password exists only where you typed it:

```powershell
$env:COLOSSUS_KB_ADMIN_USER = 'neo4j'; $s = Read-Host 'admin password' -AsSecureString; $env:COLOSSUS_KB_ADMIN_PASSWORD = [Net.NetworkCredential]::new('', $s).Password; Remove-Variable s
uv run graph/admin/migrate.py --dry-run
uv run graph/admin/migrate.py            # add --yes on production
Remove-Item Env:COLOSSUS_KB_ADMIN_USER, Env:COLOSSUS_KB_ADMIN_PASSWORD
```

Agents don't run anything in `graph/admin/`: `kb.py` is their tool, and it only uses `kb_reader` / `kb_writer`.

## Migrating the KB from staging to production (#15)

`dump.py` and `load.py` move the KB between instances without touching anything else on them. The load runs in **one transaction** and commits only if every check holds:
- every record is merged by business key, touching only the KB's own labels and types;
- all integrity checks pass;
- the target's KB, dumped again inside the transaction, is identical to the file, so a target that already holds other KB data is refused;
- the nodes and relationships of the other graphs are unchanged, per label and per type.

**Never** use Aura snapshot restore, `neo4j-admin load` or the Aura import tool on production: they replace the whole database, including the other graphs.

The commands below set the target in the session (`$env:…`), so your saved user variables keep pointing at staging until step 5.

**1. Freeze staging in the database, then dump it.** Every engineer's agent has the writer login, so a freeze on your machine alone isn't enough. As the **staging** admin, suspend the writer (Aura Query runs as the console account, so use the script):

```powershell
$env:COLOSSUS_KB_ADMIN_USER = 'neo4j'; $s = Read-Host 'staging admin password' -AsSecureString; $env:COLOSSUS_KB_ADMIN_PASSWORD = [Net.NetworkCredential]::new('', $s).Password; Remove-Variable s
uv run graph/admin/kb_users.py suspend-writer          # COLOSSUS_KB_URI is still staging
Remove-Item Env:COLOSSUS_KB_ADMIN_USER, Env:COLOSSUS_KB_ADMIN_PASSWORD
```

From now on every `kb.py write` against staging fails with an authentication error, instead of being lost silently. Tell the team. Then dump (read-only, your `kb_reader` login):

```powershell
uv run skills/knowledge/scripts/kb.py integrity
uv run graph/admin/dump.py --out .scratch/kb-dump.jsonl
```

**2. Prepare production, as its admin:**

```powershell
$env:COLOSSUS_KB_URI = 'neo4j+s://fc801360.databases.neo4j.io'; $env:COLOSSUS_KB_DATABASE = 'neo4j'
$env:COLOSSUS_KB_ADMIN_USER = 'neo4j'; $s = Read-Host 'admin password' -AsSecureString; $env:COLOSSUS_KB_ADMIN_PASSWORD = [Net.NetworkCredential]::new('', $s).Password; Remove-Variable s
uv run graph/admin/migrate.py --dry-run
uv run graph/admin/migrate.py --yes
```

**3. Load, dry run first.** The dry run does everything, including the checks, then rolls back:

```powershell
uv run graph/admin/load.py --in .scratch/kb-dump.jsonl --dry-run
uv run graph/admin/load.py --in .scratch/kb-dump.jsonl --yes
```

The output shows the merged counts, the other graphs' counts (unchanged), and `matches_dump: true`. Checking the other graphs scans their nodes and relationships twice; the dry run shows how long that takes.

Then confirm nothing was written to staging after the dump (your user variables still point at staging):

```powershell
uv run graph/admin/dump.py --out .scratch/kb-after.jsonl --compare .scratch/kb-dump.jsonl   # must say "identical"
```

**4. Create the production users**, with **new** passwords (typed at a prompt that shows `*` per character; store them in the secret store):

```powershell
uv run graph/admin/kb_users.py create --yes
```

Then close the admin session:

```powershell
Remove-Item Env:COLOSSUS_KB_ADMIN_USER, Env:COLOSSUS_KB_ADMIN_PASSWORD, Env:COLOSSUS_KB_URI, Env:COLOSSUS_KB_DATABASE
```

**5. Point your machine at production:**

```powershell
python scripts/setup_kb.py --reset
```

Enter the production URI and the new `kb_reader` and `kb_writer` passwords, then restart Cursor and Claude Code.

**Leave staging's `kb_writer` suspended** until everyone has switched: anyone still pointing at staging then gets an authentication error rather than writing to a KB that is no longer the source of truth. Reactivate it for development afterwards (`uv run graph/admin/kb_users.py activate-writer` as the staging admin); the integration tests need it.

**6. Verify on production:**

```powershell
uv run skills/knowledge/scripts/kb.py status        # kb_reader@fc801360, 46+ facts
uv run skills/knowledge/scripts/kb.py integrity     # clean
uv run scripts/check_kb_readonly.py                 # kb_reader and the MCP refuse writes; search works
uv run skills/knowledge/scripts/kb.py export --check   # the export from production matches knowledge/
```

The integration tests only run against staging (`STAGING_HOST` in the tests). To run them after the switch, reactivate staging's `kb_writer` and point a session at staging with its login.

**7. Tell the team:** run `python scripts/setup_kb.py --reset` with the production logins (Enter at the URI prompt takes production for anyone still on staging), then `python scripts/setup_kb.py --check`. Staging stays for development and future rehearsals; it is no longer the source of truth.
