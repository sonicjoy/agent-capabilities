#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""Apply graph/migrations/NNN_*.cypher to a KB instance as its admin. For humans; agents don't run graph/admin/*.

    python graph/admin/migrate.py --dry-run     show what would run
    python graph/admin/migrate.py               apply (staging)
    python graph/admin/migrate.py --yes         apply (production needs --yes)

Target instance: COLOSSUS_KB_URI and COLOSSUS_KB_DATABASE, the same settings kb.py uses.
Admin login: COLOSSUS_KB_ADMIN_USER and COLOSSUS_KB_ADMIN_PASSWORD, read from this process's environment only (never
the registry or any config file), so the admin password exists only in the terminal session where you typed it:

    $env:COLOSSUS_KB_ADMIN_USER = 'neo4j'
    $s = Read-Host 'admin password' -AsSecureString
    $env:COLOSSUS_KB_ADMIN_PASSWORD = [Net.NetworkCredential]::new('', $s).Password; Remove-Variable s
    ...
    Remove-Item Env:COLOSSUS_KB_ADMIN_USER, Env:COLOSSUS_KB_ADMIN_PASSWORD

Each migration runs one statement per transaction (schema statements can't share one with data writes) and is then
recorded as (:KbMigration {id, checksum, applied_at}). Edited or unknown migrations stop the run.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(os.path.realpath(__file__)).parents[2]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
import kb  # noqa: E402  (shared helpers: settings, statement splitting, migration planning)

ADMIN_USER, ADMIN_PASSWORD = "COLOSSUS_KB_ADMIN_USER", "COLOSSUS_KB_ADMIN_PASSWORD"
# The shared production instance (Aura instance id): applying there needs --yes.
PRODUCTION_INSTANCES = {"fc801360"}


def is_production(host: str) -> bool:
    """Match on the instance id (the first host label), so any Aura host form for that instance counts."""
    return host.lower().split(".")[0] in PRODUCTION_INSTANCES


def admin_connection() -> kb.Connection:
    uri, database = kb.env("COLOSSUS_KB_URI"), kb.env("COLOSSUS_KB_DATABASE")
    user, password = os.environ.get(ADMIN_USER), os.environ.get(ADMIN_PASSWORD)
    missing = [n for n, v in (("COLOSSUS_KB_URI", uri), ("COLOSSUS_KB_DATABASE", database),
                              (ADMIN_USER, user), (ADMIN_PASSWORD, password)) if not v]
    if missing:
        raise kb.KbError(f"missing {', '.join(missing)}; the admin login is read from this terminal session only")
    return kb.Connection(uri, user, password, database, "session COLOSSUS_KB_ADMIN_*")


def migrate(args) -> int:
    admin = admin_connection()
    if is_production(admin.host) and not args.dry_run and not args.yes:
        raise kb.KbError(f"{admin.host} is production: run with --dry-run first, then again with --yes")
    migrations = kb.load_migrations(ROOT)
    with kb.driver(admin) as drv, drv.session(database=admin.database) as s:
        todo = kb.plan_migrations(migrations, kb.applied_migrations(s))
        print(f"migrate {admin.describe()}: {len(migrations) - len(todo)} applied, {len(todo)} pending")
        for m in todo:
            statements = kb.split_statements(m.text)
            print(f"  {'would apply' if args.dry_run else 'apply'} {m.id} ({len(statements)} statements)")
            if args.dry_run:
                continue
            for st in statements:
                s.run(st).consume()
            s.run("MERGE (m:KbMigration {id: $id}) SET m.checksum = $checksum, m.applied_at = datetime()",
                  id=m.id, checksum=m.checksum).consume()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="migrate.py", description="Apply KB schema migrations as the instance admin.")
    parser.add_argument("--dry-run", action="store_true", help="show pending migrations without applying them")
    parser.add_argument("--yes", action="store_true", help="required to apply migrations to production")
    args = parser.parse_args(argv)
    try:
        return migrate(args)
    except kb.KbError as e:
        print(f"migrate.py: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        code = getattr(e, "code", None)
        if code:
            print(f"migrate.py: {code}: {getattr(e, 'message', e)}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
