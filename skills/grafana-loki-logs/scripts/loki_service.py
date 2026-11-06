#!/usr/bin/env python3
import argparse
import sys

from loki_common import LokiError, print_results, query_loki


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query Loki by app label")
    parser.add_argument("--app", required=True, help="Value for app label")
    parser.add_argument("--contains", help="Optional line substring filter (|=)")
    parser.add_argument("--hours", type=float, default=1.0, help="Lookback window in hours")
    parser.add_argument("--limit", type=int, default=80, help="Max entries")
    parser.add_argument("--direction", choices=["BACKWARD", "FORWARD"], default="BACKWARD")
    parser.add_argument("--show-labels", action="store_true")
    parser.add_argument("--max-lines", type=int, default=120)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    query = f'{{app="{esc(args.app)}"}}'
    if args.contains:
        query += f' |= "{esc(args.contains)}"'

    print(f"Using query: {query}")

    try:
        data = query_loki(
            query=query,
            hours=args.hours,
            limit=args.limit,
            direction=args.direction,
        )
    except LokiError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_results(data, show_labels=args.show_labels, max_lines=args.max_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
