#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""Load a KB dump (dump.py) into an instance, as its admin (#15). For humans; agents don't run graph/admin/*.

    python graph/admin/load.py --in .scratch/kb-dump.jsonl --dry-run     everything, then roll back
    python graph/admin/load.py --in .scratch/kb-dump.jsonl --yes         load (production needs --yes)

Target: COLOSSUS_KB_URI / _DATABASE (set them in the session to the target). Admin login: COLOSSUS_KB_ADMIN_USER /
_PASSWORD from this terminal session only, as for migrate.py. Run migrate.py on the target first.

Everything happens in ONE transaction, which commits only if all of these hold:
- every record was merged by business key (idempotent; only allowed KB labels and types are touched);
- all integrity checks pass;
- the target's KB, dumped again inside the transaction, is identical to the file (so a target with other KB data
  is refused);
- the nodes and relationships outside the KB (other graphs) are unchanged, per label and per type.
Never use Aura snapshot restore, neo4j-admin load or Aura import on production: they replace the whole database.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(os.path.realpath(__file__)).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
sys.path.insert(0, str(HERE))
import kb  # noqa: E402
import migrate  # noqa: E402  (admin login, production check)
import transfer  # noqa: E402


def load_into(tx, records: list[dict], outside_before: dict, root=ROOT) -> dict:
    """Load and verify inside one transaction; raise (so the caller rolls back) if anything doesn't hold."""
    counts = transfer.load_records(tx, records)
    problems = kb.check_problems(tx, kb.integrity_checks(root))
    if problems:
        raise kb.KbError("integrity after the load: " + "; ".join(f"{p['check']}: {p['detail']}" for p in problems[:5]))
    diff = transfer.differences(records, transfer.dump_records(tx))
    if diff:
        raise kb.KbError("the target's KB isn't identical to the dump after the load:\n  " + "\n  ".join(diff))
    outside_after = transfer.outside_counts(tx)
    if outside_after != outside_before:
        raise kb.KbError(f"data outside the KB would change: before {outside_before}, after {outside_after}")
    return counts


def main(argv: list[str] | None = None) -> int:
    kb.utf8_output()
    ap = argparse.ArgumentParser(prog="load.py", description="Load a KB dump into an instance, as its admin.")
    ap.add_argument("--in", dest="path", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true", help="do everything, verify, then roll back")
    ap.add_argument("--yes", action="store_true", help="required to load into production")
    args = ap.parse_args(argv)
    try:
        header, records = transfer.read_dump(args.path)
        admin = migrate.admin_connection()
        if migrate.is_production(admin.host) and not args.dry_run and not args.yes:
            raise kb.KbError(f"{admin.host} is production: run with --dry-run first, then again with --yes")
        if admin.host == header["source"]:
            raise kb.KbError(f"the dump comes from {admin.host} itself; point COLOSSUS_KB_URI at the target")
        with kb.driver(admin) as drv, drv.session(database=admin.database) as s:
            pending = kb.plan_migrations(kb.load_migrations(ROOT), kb.applied_migrations(s))
            if pending:
                raise kb.KbError(f"{len(pending)} migration(s) pending on the target; run graph/admin/migrate.py first")
            outside_before = s.execute_read(transfer.outside_counts)
            tx = s.begin_transaction()
            try:
                counts = load_into(tx, records, outside_before)
                tx.rollback() if args.dry_run else tx.commit()
            finally:
                if not tx.closed():
                    tx.rollback()
            after = s.execute_read(transfer.dump_records)
    except (kb.KbError, transfer.TransferError) as e:
        print(f"load.py: {e}", file=sys.stderr)
        return 2
    print(f"{'DRY RUN (rolled back)' if args.dry_run else 'loaded'}: {len(records)} records from {header['source']} "
          f"({header['dumped_at']}) into {admin.describe()}")
    report = {"merged": counts, "outside_kb_unchanged": outside_before}
    if args.dry_run:      # the checks ran inside the transaction; the target is now as before the dry run
        report["verified_before_rollback"] = True
    else:
        report["target_summary_now"] = transfer.summary(after)
        report["matches_dump"] = transfer.summary(after) == header["summary"]
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
