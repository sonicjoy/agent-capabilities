import json
import os
from datetime import datetime, timezone

import requests


class LokiError(RuntimeError):
    """Raised when Loki query fails."""


def get_env(name: str) -> str | None:
    return os.getenv(name)


def load_config() -> tuple[str, str, str]:
    addr = get_env("LOKI_ADDR")
    username = get_env("LOKI_USERNAME")
    password = get_env("LOKI_PASSWORD")

    missing = [
        key
        for key, value in (
            ("LOKI_ADDR", addr),
            ("LOKI_USERNAME", username),
            ("LOKI_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise LokiError(
            "Missing environment variables: "
            + ", ".join(missing)
            + ". Set them in your current shell/session."
        )

    return addr.rstrip("/"), username, password


def range_ns(hours: float) -> tuple[str, str]:
    if hours <= 0:
        raise LokiError("hours must be > 0")

    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int(end_ms - (hours * 3600000.0))
    start_ns = str(start_ms * 1_000_000)
    end_ns = str(end_ms * 1_000_000)
    return start_ns, end_ns


def query_loki(
    query: str,
    hours: float = 1,
    limit: int = 80,
    direction: str = "BACKWARD",
    timeout: int = 30,
) -> dict:
    addr, username, password = load_config()
    start_ns, end_ns = range_ns(hours)

    params = {
        "query": query,
        "start": start_ns,
        "end": end_ns,
        "limit": limit,
        "direction": direction,
    }
    url = f"{addr}/loki/api/v1/query_range"

    try:
        response = requests.get(
            url,
            params=params,
            auth=(username, password),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise LokiError(f"Request failed: {exc}") from exc

    if response.status_code != 200:
        body = response.text.strip()
        if len(body) > 800:
            body = body[:800] + "..."
        raise LokiError(f"Loki HTTP {response.status_code}: {body}")

    try:
        return response.json()
    except ValueError as exc:
        raise LokiError("Loki response is not valid JSON") from exc


def ns_to_iso(ns: str) -> str:
    try:
        value = int(ns)
    except (TypeError, ValueError):
        return str(ns)
    return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat()


def parse_line(raw_line: str) -> tuple[str, str | None, str | None]:
    try:
        payload = json.loads(raw_line)
    except (TypeError, ValueError):
        text = raw_line if isinstance(raw_line, str) else str(raw_line)
        return text, None, None

    if isinstance(payload, dict):
        outer_time = payload.get("time")
        log_obj = payload.get("log")
        if isinstance(log_obj, dict):
            message = log_obj.get("message")
            level = log_obj.get("level")
            logger = log_obj.get("logger")
            if isinstance(message, str):
                src = logger if isinstance(logger, str) else None
                lvl = level if isinstance(level, str) else None
                ts = outer_time if isinstance(outer_time, str) else None
                return message, ts, f"{lvl} {src}".strip() if (lvl or src) else src

        message = payload.get("message")
        if isinstance(message, str):
            return message, outer_time if isinstance(outer_time, str) else None, None

    pretty = json.dumps(payload, ensure_ascii=True)
    return pretty, None, None


def print_results(data: dict, show_labels: bool = False, max_lines: int = 120) -> None:
    results = data.get("data", {}).get("result", [])
    if not results:
        print("No matching streams.")
        return

    shown = 0
    for stream in results:
        labels = stream.get("stream", {})
        if show_labels:
            print("labels:", json.dumps(labels, ensure_ascii=True, sort_keys=True))

        for pair in stream.get("values", []):
            if not isinstance(pair, list) or len(pair) < 2:
                continue
            ts_ns, raw_line = pair[0], pair[1]
            message, parsed_time, source = parse_line(raw_line)
            timestamp = parsed_time or ns_to_iso(ts_ns)
            prefix = f"[{timestamp}]"
            if source:
                prefix += f" {source}"
            print(prefix)
            print(message)
            print("---")

            shown += 1
            if shown >= max_lines:
                print(f"Truncated output at {max_lines} lines.")
                return

    print(f"Displayed {shown} line(s).")
