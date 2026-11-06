#!/usr/bin/env python3
import argparse
import sys

from loki_common import LokiError, print_results, query_loki


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find threshold-related router log lines for statsfeed daemon"
    )
    parser.add_argument("--hours", type=float, default=24.0, help="Lookback window in hours")
    parser.add_argument("--limit", type=int, default=120, help="Max entries per query")
    parser.add_argument("--direction", choices=["BACKWARD", "FORWARD"], default="BACKWARD")
    parser.add_argument("--raw-json", action="store_true", help="Print full JSON for each query")
    parser.add_argument("--show-labels", action="store_true")
    parser.add_argument("--max-lines", type=int, default=120)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    checks = [
        (
            "threshold keyword",
            '{app="cbstats-feed-daemon-router"} |~ "(?i)threshold|thresholds"',
        ),
        (
            "prop + threshold",
            '{app="cbstats-feed-daemon-router"} |~ "(?i)prop.*threshold|threshold.*prop"',
        ),
        (
            "threshold value change markers",
            '{app="cbstats-feed-daemon-router"} |~ "(?i)threshold.*(->| to )|(->| to ).*threshold"',
        ),
    ]

    any_matches = False
    for title, query in checks:
        print(f"\n=== {title} ===")
        print(f"query: {query}")
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

        results = data.get("data", {}).get("result", [])
        if results:
            any_matches = True

        if args.raw_json:
            import json

            print(json.dumps(data, indent=2, ensure_ascii=True))
        else:
            print_results(data, show_labels=args.show_labels, max_lines=args.max_lines)

    if not any_matches:
        print("\nNo threshold-related matches found in selected window.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
