#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""Dump the Colossus KB to a JSON-lines file (#15). Read-only; for humans, agents don't run graph/admin/*.

    python graph/admin/dump.py --out .scratch/kb-dump.jsonl
    python graph/admin/dump.py --out .scratch/kb-after.jsonl --compare .scratch/kb-dump.jsonl   exit 1 if they differ

Reads the instance in COLOSSUS_KB_URI / _DATABASE with the read-only login (COLOSSUS_KB_READER_*, else the writer),
in one read transaction: integrity is checked first and the dump is refused if any check fails. The file holds every
KB node and relationship with all properties and history, keyed by business keys; see transfer.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(os.path.realpath(__file__)).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
sys.path.insert(0, str(HERE))
import kb  # noqa: E402
import transfer  # noqa: E402


def snapshot(tx, root=ROOT) -> list[dict]:
    problems = kb.check_problems(tx, kb.integrity_checks(root))
    if problems:
        raise kb.KbError(f"integrity: {len(problems)} problem(s), not dumping; run kb.py integrity")
    return transfer.dump_records(tx)


def main(argv: list[str] | None = None) -> int:
    kb.utf8_output()
    ap = argparse.ArgumentParser(prog="dump.py", description="Dump the Colossus KB to JSON lines (read-only).")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--compare", type=Path, help="an earlier dump: report any difference (e.g. writes after it)")
    args = ap.parse_args(argv)
    try:
        conn = kb.reader_connection()
        with kb.driver(conn) as drv, drv.session(database=conn.database) as s:
            records = s.execute_read(snapshot)
        header = transfer.write_dump(args.out, records, conn.host, datetime.now(timezone.utc).isoformat())
    except (kb.KbError, transfer.TransferError) as e:
        print(f"dump.py: {e}", file=sys.stderr)
        return 2
    print(f"dumped {len(records)} records from {conn.describe()} to {args.out}")
    print(json.dumps(header["summary"], indent=2))
    if args.compare:
        try:
            earlier_header, earlier = transfer.read_dump(args.compare)
        except transfer.TransferError as e:
            print(f"dump.py: {e}", file=sys.stderr)
            return 2
        diff = transfer.differences(earlier, records)
        if diff:
            print(f"DIFFERENT from {args.compare} ({earlier_header['dumped_at']}):")
            print("\n".join(f"  {d}" for d in diff))
            return 1
        print(f"identical to {args.compare} ({earlier_header['dumped_at']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
