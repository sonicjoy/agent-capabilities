#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""kb.py: the only way to read and write the Colossus knowledge graph.

Commands:
  kb.py status                                  connection, login, roles, applied migrations (no secrets)
  kb.py integrity [--json]                      run graph/schema/integrity.cypher; exit 1 if any check returns rows
  kb.py read categories
  kb.py read current-by-category [--path-prefix P] [--limit N]
  kb.py read context --path-prefix P [--limit N]  current facts under P in full, as markdown for an agent session
  kb.py read search --q TEXT [--limit N<=8]
  kb.py read fact --id ID [--as-of T | --kb-as-of T]
  kb.py read related --id ID
  kb.py read history --id ID
  kb.py write fact | retract | promote | link | unlink | component | repo | category   (kb.py write <cmd> --help)
  kb.py export [--out DIR] [--check] [--allow-removals]           regenerate knowledge/colossus-bets/ (export/graph_to_markdown.py)
Writes run in one transaction, check integrity before commit, and roll back on any problem; --dry-run always
rolls back. COLOSSUS_KB_FREEZE=1 refuses every write.
Reads print compact text by default and JSON with --json. Exit codes: 0 ok, 1 nothing found / problems, 2 error.
Reads, status and integrity use the read-only login COLOSSUS_KB_READER_USER/_PASSWORD when set (else the writer).

kb.py only ever uses the KB logins (kb_writer, or kb_reader). Schema migrations need the instance admin and live in
graph/admin/migrate.py, a separate script for humans that agents don't run.

kb.py never runs free-form Cypher: every query comes from a named file under graph/.
Settings come from COLOSSUS_KB_URI / _USER / _PASSWORD / _DATABASE (see graph/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ENV_KEYS = ("COLOSSUS_KB_URI", "COLOSSUS_KB_USER", "COLOSSUS_KB_PASSWORD", "COLOSSUS_KB_DATABASE")
READER_KEYS = ("COLOSSUS_KB_READER_USER", "COLOSSUS_KB_READER_PASSWORD")
TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
LIBRARY = "colossus-bets"
SEARCH_LIMIT_MAX = 8
CATEGORY_LIMIT_MAX = 200
MAX_WORDS = 8
MIN_WORD_LEN = 3
# Shorter words match inside unrelated words (substring search), so only these known acronyms are kept.
SHORT_WORDS = {"ru", "bb", "ou"}
# Simple English stems: also search "settle" for "settlement", "restart" for "restarts". Longest suffix first.
STEM_SUFFIXES = ("ments", "ment", "ings", "ing", "ies", "es", "ed", "s")
# Words too common to narrow a search (they'd match nearly every fact).
STOPWORDS = {"and", "are", "for", "from", "not", "per", "the", "via", "with"}
MIGRATION_FILE = re.compile(r"^\d{3}_[a-z0-9_]+\.cypher$")
HEADING = re.compile(r"^(#{1,6})(\s.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")


def utf8_output() -> None:
    """Print UTF-8 whatever the console code page. On Windows, piped output otherwise uses the ANSI code page
    (cp1252), so facts with curly quotes or dashes come out garbled, or a character can't be printed at all."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)     # absent on replaced streams (e.g. pytest capture)
        if reconfigure:
            reconfigure(encoding="utf-8")


class KbError(Exception):
    """A problem the user can fix (configuration, refused operation). Printed without a traceback."""


# ---------------------------------------------------------------- repo and files

def repo_root(start: Path | None = None) -> Path:
    """The agent-capabilities checkout: the first parent of this file (junctions resolved) that has graph/migrations."""
    override = os.environ.get("COLOSSUS_KB_REPO")
    if override:
        return Path(override)
    here = Path(os.path.realpath(start or __file__))
    for parent in here.parents:
        if (parent / "graph" / "migrations").is_dir():
            return parent
    raise KbError(f"can't find graph/migrations above {here}; set COLOSSUS_KB_REPO")


def split_statements(text: str) -> list[str]:
    """Split a .cypher file on `;` at the end of a line. Chunks that hold only `//` comments are dropped."""
    out = []
    for chunk in re.split(r";[ \t]*(?://[^\n]*)?(?:\r?\n|$)", text):
        code = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("//")).strip()
        if code:
            out.append(code)
    return out


def parse_checks(text: str) -> list[tuple[str, str]]:
    """integrity.cypher -> [(name, query)], split on `// check: <name>` headers; the header comment lines are kept."""
    parts = re.split(r"^// check: *(\S+)[ \t]*\r?$", text, flags=re.M)
    checks = [(parts[i], parts[i + 1].strip().rstrip(";").strip()) for i in range(1, len(parts), 2)]
    names = [n for n, _ in checks]
    if len(names) != len(set(names)):
        raise KbError("duplicate check names in integrity.cypher")
    return checks


@dataclass(frozen=True)
class Migration:
    id: str
    path: Path
    text: str

    @property
    def checksum(self) -> str:
        # LF-normalised so a CRLF checkout can't change the checksum of an applied migration.
        return hashlib.sha256(self.text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def load_migrations(root: Path) -> list[Migration]:
    files = sorted(p for p in (root / "graph" / "migrations").iterdir() if MIGRATION_FILE.match(p.name))
    numbers = [p.name[:3] for p in files]
    if len(numbers) != len(set(numbers)):
        raise KbError(f"two migrations share a number: {numbers}")
    return [Migration(p.stem, p, p.read_text(encoding="utf-8")) for p in files]


def plan_migrations(migrations: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """Migrations still to apply. Raises if an applied one changed or a recorded one is missing from the repo."""
    by_id = {m.id: m for m in migrations}
    unknown = sorted(set(applied) - set(by_id))
    if unknown:
        raise KbError(f"the database has migrations this checkout doesn't: {unknown}; update your checkout")
    changed = [m.id for m in migrations if m.id in applied and applied[m.id] != m.checksum]
    if changed:
        raise KbError(f"applied migrations were edited: {changed}; restore them and add a new migration instead")
    return [m for m in migrations if m.id not in applied]


def load_template(root: Path, kind: str, name: str) -> str:
    """A named query from graph/queries/<kind>/<name>.cypher. Only plain names are accepted."""
    if kind not in ("read", "write") or not TEMPLATE_NAME.match(name):
        raise KbError(f"invalid template {kind}/{name}")
    path = root / "graph" / "queries" / kind / f"{name}.cypher"
    if not path.is_file():
        raise KbError(f"no template {kind}/{name}")
    statements = split_statements(path.read_text(encoding="utf-8"))
    if len(statements) != 1:
        raise KbError(f"template {kind}/{name} must hold exactly one statement")
    return statements[0]


# ---------------------------------------------------------------- configuration

def _windows_user_env(name: str) -> str | None:
    """Read a user-level environment variable straight from the registry (for apps started before it was set)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def env_with_source(name: str) -> tuple[str | None, str]:
    """A setting and where it came from. The process environment wins; an empty value there counts as unset,
    so the Windows user environment (registry) is used instead."""
    value = os.environ.get(name)
    if value:
        return value, "environment"
    value = _windows_user_env(name)
    return (value, "Windows user registry") if value else (None, "unset")


def read_secret(prompt: str) -> str:
    """A password typed at the terminal, echoed as one * per character (so a paste is visibly there) and never
    printed. Backspace deletes; Ctrl+C cancels. Without an interactive terminal it reads hidden input instead."""
    import getpass
    if not sys.stdin.isatty():
        return getpass.getpass(prompt)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if sys.platform == "win32":
        import msvcrt
        read = msvcrt.getwch
        raw = None
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        raw = termios.tcgetattr(fd)
        tty.setraw(fd)
        read = lambda: sys.stdin.read(1)  # noqa: E731
    chars: list[str] = []
    try:
        while True:
            ch = read()
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":                              # Ctrl+C
                raise KeyboardInterrupt
            if ch in ("\x00", "\xe0"):                    # Windows: arrow/function key prefix; skip the key code
                read()
                continue
            if ch in ("\x08", "\x7f"):                    # Backspace
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif ch >= " ":
                chars.append(ch)
                sys.stdout.write("*")
            sys.stdout.flush()
    finally:
        if raw is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, raw)
        sys.stdout.write("\n")
        sys.stdout.flush()
    return "".join(chars)


# Instances that held the KB once but no longer do (Aura instance id -> what they are now).
RETIRED_KB_HOSTS = {"839b9d82": "staging, no longer the KB since 2026-10-08; production is fc801360"}


def retired_host(uri: str | None) -> str | None:
    """Why `uri` is a retired KB instance, or None."""
    host = (urlparse(uri).hostname or "") if uri else ""
    return RETIRED_KB_HOSTS.get(host.lower().split(".")[0])


def deliberate_session() -> bool:
    """The integration tests (KB_IT=1) point the session at staging on purpose; the warnings stay quiet there. Admin
    sessions (graph/admin/*, whose login kb.py never reads) are covered by the warning's "on purpose" wording."""
    return os.environ.get("KB_IT") == "1"


def stale_settings() -> list[str]:
    """KB settings this process holds that differ from the saved user environment (Windows), including ones removed
    since (e.g. a leftover COLOSSUS_KB_FREEZE): the app started before they changed and still uses the old values
    until it restarts. Only names."""
    if sys.platform != "win32":
        return []
    return [n for n in ENV_KEYS + READER_KEYS + ("COLOSSUS_KB_FREEZE",)
            if os.environ.get(n) and os.environ[n] != (_windows_user_env(n) or None)]


def warn_settings() -> list[str]:
    """Warn on stderr (names and hosts only) about settings that are probably not what the user wants. Returns the
    stale names."""
    if deliberate_session():
        return []
    stale = stale_settings()
    if stale:
        print(f"kb.py: WARNING: this app was started before {', '.join(stale)} changed (saved settings differ) and "
              f"still uses the old values; restart it (Cursor / Claude Code / the terminal), or ignore this if you "
              f"set them in this session on purpose", file=sys.stderr)
    why = retired_host(env("COLOSSUS_KB_URI"))
    if why:
        print(f"kb.py: WARNING: COLOSSUS_KB_URI points at {urlparse(env('COLOSSUS_KB_URI')).hostname} ({why}). "
              f"Run python scripts/setup_kb.py --reset and choose production, unless you use staging on purpose "
              f"(tests, rehearsals)", file=sys.stderr)
    return stale


def env(name: str) -> str | None:
    return env_with_source(name)[0]


@dataclass(frozen=True)
class Connection:
    uri: str
    user: str
    password: str = field(repr=False)
    database: str
    source: str

    @property
    def host(self) -> str:
        return urlparse(self.uri).hostname or ""

    def describe(self) -> str:
        return f"{self.user}@{self.host}/{self.database} ({self.source})"


def writer_connection() -> Connection:
    found = {k: env_with_source(k) for k in ENV_KEYS}
    missing = [k for k, (v, _) in found.items() if not v]
    if missing:
        raise KbError(f"missing {', '.join(missing)}; see skills/knowledge/scripts/README.md")
    sources = sorted({src for _, src in found.values()})
    return Connection(found["COLOSSUS_KB_URI"][0], found["COLOSSUS_KB_USER"][0], found["COLOSSUS_KB_PASSWORD"][0],
                      found["COLOSSUS_KB_DATABASE"][0], "COLOSSUS_KB_* from " + " + ".join(sources))


def reader_connection() -> Connection:
    """Read-only login for reads, status and integrity: COLOSSUS_KB_READER_* when set, else the writer.
    With the reader set, a read-only setup doesn't need the writer password at all."""
    user, user_src = env_with_source("COLOSSUS_KB_READER_USER")
    password, _ = env_with_source("COLOSSUS_KB_READER_PASSWORD")
    if not (user and password):
        return writer_connection()
    found = {k: env_with_source(k) for k in ("COLOSSUS_KB_URI", "COLOSSUS_KB_DATABASE")}
    missing = [k for k, (v, _) in found.items() if not v]
    if missing:
        raise KbError(f"missing {', '.join(missing)}; see skills/knowledge/scripts/README.md")
    return Connection(found["COLOSSUS_KB_URI"][0], user, password, found["COLOSSUS_KB_DATABASE"][0],
                      f"COLOSSUS_KB_READER_* from {user_src}")


def driver(conn: Connection):
    from neo4j import GraphDatabase
    return GraphDatabase.driver(conn.uri, auth=(conn.user, conn.password), notifications_min_severity="OFF")


# ---------------------------------------------------------------- commands

def applied_migrations(session) -> dict[str, str]:
    rows = session.run("MATCH (m:KbMigration) RETURN m.id AS id, m.checksum AS checksum")
    return {r["id"]: r["checksum"] for r in rows}


def cmd_status(args, root: Path) -> int:
    stale = stale_settings()                     # main() has already warned on stderr
    conn = reader_connection()
    with driver(conn) as drv, drv.session(database=conn.database) as s:
        me = s.run("SHOW CURRENT USER YIELD user, roles").single()
        applied = applied_migrations(s)
        counts = s.run("RETURN COUNT { (:KbCategory) } AS categories, COUNT { (:KbFact) } AS facts, "
                       "COUNT { (:KbCurrent) } AS current").single()
    pending = [m.id for m in load_migrations(root) if m.id not in applied]
    out = {"connection": conn.describe(), "user": me["user"], "roles": me["roles"],
           "migrations_applied": sorted(applied), "migrations_pending": pending,
           "categories": counts["categories"], "facts": counts["facts"], "current_versions": counts["current"]}
    if stale:
        out["stale_settings"] = stale
    print(json.dumps(out, indent=2))
    return 0


def integrity_checks(root: Path) -> list[tuple[str, str]]:
    return parse_checks((root / "graph" / "schema" / "integrity.cypher").read_text(encoding="utf-8"))


def check_problems(tx, checks: list[tuple[str, str]]) -> list[dict]:
    """Run every check inside one transaction (one consistent snapshot)."""
    return [{"check": name, "detail": r["detail"]} for name, query in checks for r in tx.run(query)]


def run_integrity(session, root: Path) -> tuple[int, list[dict]]:
    """(number of checks, problems). One read transaction: the database refuses any write, and every check sees
    the same snapshot, so a write landing between checks can't cause a false or missed result."""
    checks = integrity_checks(root)
    return len(checks), session.execute_read(check_problems, checks)


# ---------------------------------------------------------------- reads

def search_words(q: str) -> list[list[str]]:
    """The query as groups of variants, one group per word: [[word, stem?], ...]. Lower-cased; words shorter than
    MIN_WORD_LEN (except SHORT_WORDS) and stopwords dropped; duplicates removed; at most MAX_WORDS groups.
    The template seeks the index on every variant but scores each word once, by its best variant."""
    groups: list[list[str]] = []
    for word in re.findall(r"\w+", q.lower()):
        if (len(word) < MIN_WORD_LEN and word not in SHORT_WORDS) or word in STOPWORDS:
            continue
        if any(word in g for g in groups):
            continue
        group = [word]
        for suffix in STEM_SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 4:
                group.append(word[: -len(suffix)] + ("y" if suffix == "ies" else ""))
                break
        groups.append(group)
    return groups[:MAX_WORDS]


def parse_instant(value: str):
    """--as-of / --kb-as-of as a time-zone-aware datetime, passed to Cypher as a typed value (no second parser).
    A date means midnight UTC; a datetime without a time zone is taken as UTC."""
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value)  # 3.10 rejects Z
    except ValueError:
        raise KbError(f"not an ISO date or datetime: {value!r} (e.g. 2026-03-01 or 2026-03-01T12:00:00Z)")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_rows(tx, root: Path, name: str, **params) -> list[dict]:
    return [r.data() for r in tx.run(load_template(root, "read", name), **params)]


def read_current_by_category(tx, root: Path, path_prefix: str = "", limit: int = 50) -> list[dict]:
    return read_rows(tx, root, "current_by_category", path_prefix=path_prefix.strip("/"),
                     limit=max(1, min(limit, CATEGORY_LIMIT_MAX)))


def read_context(tx, root: Path, path_prefix: str, limit: int = CATEGORY_LIMIT_MAX) -> list[dict]:
    if not path_prefix.strip("/"):
        raise KbError("context needs a category, e.g. --path-prefix technical/workflow (the whole library is too big)")
    return read_rows(tx, root, "context", path_prefix=path_prefix.strip("/"),
                     limit=max(1, min(limit, CATEGORY_LIMIT_MAX)))


def read_categories(tx, root: Path, library: str = LIBRARY) -> list[dict]:
    return read_rows(tx, root, "categories", library=library)


def read_search(tx, root: Path, q: str, limit: int = SEARCH_LIMIT_MAX) -> list[dict]:
    words = search_words(q)
    if not words:
        raise KbError(f"search needs a word of {MIN_WORD_LEN}+ characters that isn't a stopword")
    return read_rows(tx, root, "search", words=words, limit=max(1, min(limit, SEARCH_LIMIT_MAX)))


def read_fact(tx, root: Path, fact_id: str, as_of: str | None = None, kb_as_of: str | None = None) -> dict | None:
    if as_of and kb_as_of:
        raise KbError("use --as-of or --kb-as-of, not both")
    if as_of:
        rows = read_rows(tx, root, "fact_as_of", id=fact_id, at=parse_instant(as_of))
    elif kb_as_of:
        rows = read_rows(tx, root, "fact_kb_as_of", id=fact_id, at=parse_instant(kb_as_of))
    else:
        rows = read_rows(tx, root, "fact", id=fact_id)
    return rows[0] if rows else None


def read_related(tx, root: Path, fact_id: str) -> dict | None:
    rows = read_rows(tx, root, "related", id=fact_id)
    return rows[0] if rows else None


def read_history(tx, root: Path, fact_id: str) -> list[dict]:
    return read_rows(tx, root, "history", id=fact_id)


def missing_fact_message(tx, root: Path, fact_id: str, when=None) -> str:
    """Why `read fact` found nothing: no such fact, nothing at that time, or no current version (e.g. retracted)."""
    if not read_history(tx, root, fact_id):
        return f"no fact {fact_id!r}"
    if when:
        return f"no version of {fact_id!r} at {when}; see: kb.py read history --id {fact_id}"
    return f"no current version of {fact_id!r} (retracted?); see: kb.py read history --id {fact_id}"


def _json_default(value):
    iso = getattr(value, "iso_format", None) or getattr(value, "isoformat", None)  # neo4j.time / Python datetimes
    return iso() if iso else str(value)


def _date(value) -> str:
    return _json_default(value)[:10] if value is not None else "-"


def format_list(rows: list[dict]) -> str:
    if not rows:
        return "(no facts)"
    lines = []
    for r in rows:
        score = f" score {r['score']}" if "score" in r else ""
        lines.append(f"- {r['id']}: {r['title']} [{r['category']}, {r['kind']}]{score}\n  {r['summary']}")
    return "\n".join(lines)


def format_categories(rows: list[dict]) -> str:
    """The tree, indented by depth; leaves (where facts go) are marked with their fact count."""
    return "\n".join("  " * r["path"].count("/") + r["path"]
                     + (f"  [leaf, {r['facts']} fact{'' if r['facts'] == 1 else 's'}]" if r["leaf"] else "") + f": {r['title']}" for r in rows)


def format_fact(row: dict) -> str:
    v = row["version"]
    out = [f"# {v['title']}  ({row['id']}, {row['category']})", v["summary"], "", v["statement"], "",
           f"version {v['version_id']} | kind {v['kind']} | status {v['status']} ({v['change_type']}) | "
           f"confidence {v['confidence']} | via {v['via']}",
           f"valid {_date(v['valid_from'])} -> {_date(v['valid_to'])} | "
           f"recorded {_date(v['recorded_at'])} -> {_date(v['recorded_to'])}",
           f"sources: {', '.join(v['source_refs'])} ({v['source_type']}) | author {row['author'] or '-'}"
           + (f" | approved by {', '.join(row['approved_by'])}" if row["approved_by"] else "")
           + (f" (recorded by {v['approval_recorded_by']}, evidence: {v['approval_evidence']})"
              if v.get("approval_recorded_by") else "")]
    for key in ("why", "context", "alternatives", "trade_offs", "revisit_if"):
        if v.get(key):
            out.append(f"{key}: {v[key]}")
    if v.get("keywords"):
        out.append("keywords: " + ", ".join(v["keywords"]))
    return "\n".join(out)


def shift_headings(text: str, top: int) -> str:
    """Move every heading (outside code fences) down so the highest one is level `top` (at most h6)."""
    lines, fenced, levels = text.split("\n"), False, []
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := HEADING.match(line)):
            levels.append(len(m.group(1)))
    shift = max(0, top - min(levels)) if levels else 0
    if not shift:
        return text
    out, fenced = [], False
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := HEADING.match(line)):
            line = "#" * min(6, len(m.group(1)) + shift) + m.group(2)
        out.append(line)
    return "\n".join(out)


def format_context(path_prefix: str, rows: list[dict]) -> str:
    """Full statements under one heading, read live from the graph: what a session start loads (#19)."""
    prefix = path_prefix.strip("/") or "(whole library)"
    out = [f"# Colossus KB: {prefix}", "",
           f"Read live from the Colossus KB graph (`kb.py read context --path-prefix {prefix}`), the source of truth. "
           "Change it with the `knowledge` skill."]
    if not rows:
        return "\n".join(out + ["", "(no current facts)"])
    for r in rows:
        out += ["", "---", "", f"## {r['title']}", f"`{r['id']}` ({r['kind']}). {r['summary']}", "",
                shift_headings(r["statement"].strip(), 3)]
    return "\n".join(out)


def format_related(row: dict) -> str:
    out = [f"related to {row['id']}:"]
    out += [f"- {f['direction']} {f['rel'] or '?'}: {f['id']}: {f['title']}" for f in row["facts"]] or ["- (no related facts)"]
    out += [f"- describes {c['name']} ({c['kind']}) in {', '.join(c['repos']) or '-'}" for c in row["components"]]
    out += [f"- implemented in {r['path']}" for r in row["repos"]]
    return "\n".join(out)


def format_history(rows: list[dict]) -> str:
    return "\n".join(
        f"- {r['version_id']} {r['status']}{' (current)' if r['current'] else ''} {r['change_type']}: {r['title']} | "
        f"valid {_date(r['valid_from'])}->{_date(r['valid_to'])} "
        f"recorded {_date(r['recorded_at'])}->{_date(r['recorded_to'])}"
        + (f" | why: {r['why']}" if r["why"] else "")
        + (f" | approved by {', '.join(r['approved_by'])}" if r.get("approved_by") else "")
        + (f" (recorded by {r['approval_recorded_by']}, evidence: {r['approval_evidence']})"
           if r.get("approval_recorded_by") else "")
        for r in rows)


def cmd_read(args, root: Path) -> int:
    conn = reader_connection()
    with driver(conn) as drv, drv.session(database=conn.database) as s:
        if args.what == "categories":
            result = s.execute_read(read_categories, root)
            text, found = format_categories(result), True
        elif args.what == "current-by-category":
            result = s.execute_read(read_current_by_category, root, args.path_prefix, args.limit)
            text, found = format_list(result), True
            limit = max(1, min(args.limit, CATEGORY_LIMIT_MAX))
            if len(result) == limit:
                note = f"(first {limit} facts; more may exist: use --limit, max {CATEGORY_LIMIT_MAX}, or a narrower --path-prefix)"
                text += "\n" + note
                if args.json:
                    print(note, file=sys.stderr)
        elif args.what == "context":
            result = s.execute_read(read_context, root, args.path_prefix, args.limit)
            text, found = format_context(args.path_prefix, result), bool(result)
            if len(result) == max(1, min(args.limit, CATEGORY_LIMIT_MAX)):
                note = f"(first {len(result)} facts; more may exist: use a narrower --path-prefix)"
                text += "\n\n" + note
                if args.json:
                    print(note, file=sys.stderr)
        elif args.what == "search":
            result = s.execute_read(read_search, root, args.q, args.limit)
            text, found = format_list(result), True
        elif args.what == "fact":
            result = s.execute_read(read_fact, root, args.id, args.as_of, args.kb_as_of)
            found = result is not None
            text = format_fact(result) if found else s.execute_read(
                missing_fact_message, root, args.id, args.as_of or args.kb_as_of)
        elif args.what == "related":
            result = s.execute_read(read_related, root, args.id)
            text, found = (format_related(result) if result else f"no fact {args.id!r}"), result is not None
        else:
            result = s.execute_read(read_history, root, args.id)
            text, found = (format_history(result) if result else f"no fact {args.id!r}"), bool(result)
    print(json.dumps(result, indent=2, default=_json_default, ensure_ascii=False) if args.json else text)
    return 0 if found else 1


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value is not None else None


def _expected(value: str | None) -> str | None:
    return None if value in (None, "", "none") else value


STATEMENT_FILE_MAX = 64 * 1024


def kb_identity() -> str:
    """Who is running kb.py: COLOSSUS_KB_AUTHOR, else `git config --global user.email`. Authors and approvers come
    from here, not from what's typed. An author who promotes their own draft names the confirmer with --confirmed-by,
    and the KB records that the author recorded it."""
    value = env("COLOSSUS_KB_AUTHOR")
    if not value:
        import subprocess
        try:
            value = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True,
                                   timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            value = ""
    if not value:
        raise KbError("can't tell who you are: set COLOSSUS_KB_AUTHOR (your email) or git config --global user.email")
    return value.lower()


def _actor(given: str | None, role: str) -> str:
    me = kb_identity()
    if given and given.lower() != me:
        raise KbError(f"--{role} {given!r} isn't you ({me}); kb.py records the person running it")
    return me


def cmd_write(args, root: Path) -> int:
    import kbwrite
    if env("COLOSSUS_KB_FREEZE") == "1":
        raise KbError("writes are frozen (COLOSSUS_KB_FREEZE=1), e.g. during a migration")
    if args.what == "fact":
        statement = args.statement
        if args.statement_file:
            path = Path(args.statement_file)
            if not path.is_file() or path.stat().st_size > STATEMENT_FILE_MAX:
                raise KbError(f"--statement-file must be an existing file under {STATEMENT_FILE_MAX // 1024} KB")
            statement = path.read_text(encoding="utf-8")
        inp = kbwrite.FactInput(
            id=args.id, why=args.why, source_type=args.source_type, source_refs=args.source_ref or [],
            author=_actor(args.author, "author"), author_name=args.author_name, via=args.via, category=args.category, kind=args.kind,
            title=args.title, summary=args.summary, statement=statement, keywords=_csv(args.keywords),
            context=args.context, alternatives=args.alternatives, trade_offs=args.trade_offs,
            revisit_if=args.revisit_if, confidence=args.confidence, change_type=args.change_type,
            valid_from=parse_instant(args.valid_from) if args.valid_from else None,
            expected_current=_expected(args.expected_current), draft=args.draft)
        work = lambda tx: kbwrite.write_fact(tx, root, inp)
    elif args.what == "retract":
        author = _actor(args.author, "author")
        work = lambda tx: kbwrite.retract(tx, root, args.id, args.why, args.source_ref or [], author,
                                          _expected(args.expected_current), args.never_valid)
    elif args.what == "promote":
        approver = _actor(args.approver, "approver")
        work = lambda tx: kbwrite.promote(tx, root, args.version_id, approver, _expected(args.expected_current),
                                          args.approver_name, confirmed_by=args.confirmed_by, evidence=args.evidence,
                                          confirmed_by_name=args.confirmed_by_name)
    elif args.what == "link":
        work = lambda tx: kbwrite.link(tx, root, args.type, args.source, args.target, args.rel)
    elif args.what == "unlink":
        work = lambda tx: kbwrite.unlink(tx, root, args.type, args.source, args.target, args.rel)
    elif args.what == "component":
        work = lambda tx: kbwrite.upsert_component(tx, root, args.name, args.kind, args.description)
    elif args.what == "repo":
        work = lambda tx: kbwrite.upsert_repo(tx, root, args.path, args.web_url)
    else:
        work = lambda tx: kbwrite.create_category(tx, root, args.path, args.title, args.description)
    conn = writer_connection()
    with driver(conn) as drv, drv.session(database=conn.database) as s:
        tx = s.begin_transaction()
        try:
            result = work(tx)
            if args.dry_run:
                tx.rollback()
            else:
                tx.commit()
        finally:
            if not tx.closed():
                tx.rollback()
    result["committed"] = not args.dry_run
    if args.json:
        print(json.dumps(result, indent=2, default=_json_default, ensure_ascii=False))
    else:
        print(("DRY RUN (rolled back): " if args.dry_run else "written: ")
              + ", ".join(f"{k}={_json_default(v) if v is not None else '-'}" for k, v in result.items() if k != "committed"))
    return 0


def cmd_integrity(args, root: Path) -> int:
    conn = reader_connection()
    with driver(conn) as drv, drv.session(database=conn.database) as s:
        n_checks, problems = run_integrity(s, root)
    if args.json:
        print(json.dumps({"checks": n_checks, "problems": problems}, indent=2))
    elif problems:
        print(f"integrity: {len(problems)} problem(s) in {n_checks} checks")
        for p in problems:
            print(f"  {p['check']}: {p['detail']}")
    else:
        print(f"integrity: clean ({n_checks} checks)")
    return 1 if problems else 0


def cmd_export(args, root: Path) -> int:
    """Run export/graph_to_markdown.py from this checkout. It imports `kb`; register this module under that name so
    both share one KbError (kb.py may be running as __main__)."""
    import importlib.util
    sys.modules.setdefault("kb", sys.modules[__name__])
    spec = importlib.util.spec_from_file_location("kb_export", root / "export" / "graph_to_markdown.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    argv = ((["--out", args.out] if args.out else []) + (["--check"] if args.check else [])
            + (["--allow-removals"] if args.allow_removals else []))
    return exporter.main(argv, root)


def main(argv: list[str] | None = None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(prog="kb.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="connection, login, migrations, counts")
    p = sub.add_parser("integrity", help="run graph/schema/integrity.cypher")
    p.add_argument("--json", action="store_true")
    read = sub.add_parser("read", help="read the KB (current facts, search, one fact, related, history)")
    reads = read.add_subparsers(dest="what", required=True)
    reads.add_parser("categories", help="the category tree; facts go in leaf categories")
    p = reads.add_parser("current-by-category", help="current facts in a category subtree")
    p.add_argument("--path-prefix", default="", help="e.g. business/pools or technical; empty = everything")
    p.add_argument("--limit", type=int, default=50)
    p = reads.add_parser("context", help="current facts under a category in full, as markdown for an agent session")
    p.add_argument("--path-prefix", required=True, help="e.g. technical/workflow")
    p.add_argument("--limit", type=int, default=CATEGORY_LIMIT_MAX)
    p = reads.add_parser("search", help=f"search current facts (at most {SEARCH_LIMIT_MAX} results)")
    p.add_argument("--q", required=True)
    p.add_argument("--limit", type=int, default=SEARCH_LIMIT_MAX)
    p = reads.add_parser("fact", help="one fact: current version, or as of a date")
    p.add_argument("--id", required=True)
    when = p.add_mutually_exclusive_group()
    when.add_argument("--as-of", help="business time: the rule in force on this date, by today's knowledge")
    when.add_argument("--kb-as-of", help="record time: what the KB said on this date")
    for name, help_ in (("related", "one hop: related facts, components, repos"), ("history", "every version, oldest first")):
        p = reads.add_parser(name, help=help_)
        p.add_argument("--id", required=True)
    for p in reads.choices.values():
        p.add_argument("--json", action="store_true")

    write = sub.add_parser("write", help="change the KB (only after the user confirms; see the knowledge skill)")
    writes = write.add_subparsers(dest="what", required=True)
    p = writes.add_parser("fact", help="create a fact, or write a new version (change / correction)")
    p.add_argument("--id", required=True, help="kebab slug; permanent")
    p.add_argument("--category", help="leaf category path (required for a new fact; a different one moves the fact)")
    p.add_argument("--kind", help="rule | decision | description | procedure | glossary | lesson")
    p.add_argument("--title")
    p.add_argument("--summary", help="one line, readable by a PM")
    p.add_argument("--statement", help="markdown body")
    p.add_argument("--statement-file", help="read the statement from a file instead")
    p.add_argument("--keywords", help="comma-separated")
    p.add_argument("--why", required=True, help="why this version exists")
    for name in ("context", "alternatives", "trade-offs", "revisit-if"):
        p.add_argument(f"--{name}")
    p.add_argument("--source-type", required=True, help="e.g. mr, work_item, code, db_query, conversation")
    p.add_argument("--source-ref", action="append", help="URL, MR, work item, file path; repeat for several")
    p.add_argument("--confidence", default="verified", help="verified | inferred")
    p.add_argument("--author", help="defaults to you (COLOSSUS_KB_AUTHOR or git user.email); anyone else is refused")
    p.add_argument("--author-name")
    p.add_argument("--via", required=True, help="human | agent")
    p.add_argument("--change-type", help="change (the rule changed; default) | correction (the KB was wrong)")
    p.add_argument("--valid-from", help="when the rule took effect (ISO date/datetime; default now, or the corrected "
                                        "version's start for a correction)")
    p.add_argument("--expected-current", help="the version you are replacing (from read fact / history); 'none' for new")
    p.add_argument("--draft", action="store_true", help="save as a draft (always the case under business/pools)")
    p = writes.add_parser("retract", help="the rule no longer applies (or, with --never-valid, never did)")
    p.add_argument("--id", required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--source-ref", action="append")
    p.add_argument("--author", help="defaults to you; anyone else is refused")
    p.add_argument("--expected-current", required=True)
    p.add_argument("--never-valid", action="store_true", help="exclude it from business time entirely")
    p = writes.add_parser("promote", help="make a draft active; approved by you, or, if you wrote it, by the person "
                                          "named in --confirmed-by")
    p.add_argument("--version-id", required=True)
    p.add_argument("--approver", help="defaults to you; anyone else is refused")
    p.add_argument("--approver-name")
    p.add_argument("--confirmed-by", help="only if you wrote the draft, and then required: email of the person who "
                                          "confirmed it, already in the KB (or give --confirmed-by-name)")
    p.add_argument("--confirmed-by-name", help="their name, to add a --confirmed-by person the KB doesn't know yet")
    p.add_argument("--evidence", help="with --confirmed-by: http(s) link to their confirmation, e.g. a work-item "
                                      "comment")
    p.add_argument("--expected-current", required=True, help="the fact's latest version now, or 'none'")
    p = writes.add_parser("link", help="relates_to (fact->fact, --rel) | describes (fact->component) | "
                                       "implemented_in (fact/component->repo)")
    p.add_argument("--type", required=True, choices=["relates_to", "describes", "implemented_in"])
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--to", dest="target", required=True)
    p.add_argument("--rel", help="depends_on | see_also | contradicts | example_of (relates_to only)")
    p = writes.add_parser("unlink", help="remove a mistaken link (relates_to needs --rel)")
    p.add_argument("--type", required=True, choices=["relates_to", "describes", "implemented_in"])
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--to", dest="target", required=True)
    p.add_argument("--rel")
    p = writes.add_parser("component", help="create or update a system component")
    p.add_argument("--name", required=True)
    p.add_argument("--kind")
    p.add_argument("--description")
    p = writes.add_parser("repo", help="create or update a code repo")
    p.add_argument("--path", required=True, help="e.g. colossus/cbtote")
    p.add_argument("--web-url")
    p = writes.add_parser("category", help="create a leaf category (its parent must hold no facts)")
    p.add_argument("--path", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--description")
    for p in writes.choices.values():
        p.add_argument("--dry-run", action="store_true", help="run everything, show the result, then roll back")
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("export", help="regenerate knowledge/colossus-bets/ from the current versions")
    p.add_argument("--out", help="default: knowledge/colossus-bets in this checkout")
    p.add_argument("--check", action="store_true", help="compare only; exit 1 if the files differ from the graph")
    p.add_argument("--allow-removals", action="store_true", help="allow removing more than 3 stale files")
    args = parser.parse_args(argv)
    warn_settings()
    try:
        root = repo_root()
        return {"status": cmd_status, "integrity": cmd_integrity, "read": cmd_read, "write": cmd_write,
                "export": cmd_export}[args.command](args, root)
    except KbError as e:
        print(f"kb.py: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # driver errors: show the Neo4j code, not a traceback
        code = getattr(e, "code", None)
        if code:
            print(f"kb.py: {code}: {getattr(e, 'message', e)}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
