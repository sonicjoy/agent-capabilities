#!/usr/bin/env python3
import argparse
import json
import sys

from loki_common import LokiError, print_results, query_loki


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic Loki query helper")
    parser.add_argument("--query", required=True, help="LogQL query")
    parser.add_argument("--hours", type=float, default=1.0, help="Lookback window in hours")
    parser.add_argument("--limit", type=int, default=80, help="Max entries")
    parser.add_argument(
        "--direction",
        choices=["BACKWARD", "FORWARD"],
        default="BACKWARD",
        help="Result direction",
    )
    parser.add_argument("--raw-json", action="store_true", help="Print full JSON response")
    parser.add_argument("--show-labels", action="store_true", help="Print stream labels")
    parser.add_argument("--max-lines", type=int, default=120, help="Display cap for formatted mode")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        data = query_loki(
            query=args.query,
            hours=args.hours,
            limit=args.limit,
            direction=args.direction,
        )
    except LokiError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.raw_json:
        print(json.dumps(data, indent=2, ensure_ascii=True))
    else:
        print_results(data, show_labels=args.show_labels, max_lines=args.max_lines)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
