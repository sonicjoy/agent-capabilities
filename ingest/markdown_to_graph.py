#!/usr/bin/env python3
"""One-off load of the legacy markdown KB (knowledge/colossus-bets/) into the graph (#7).

    python ingest/markdown_to_graph.py --report ingest/report.md      plan only: parse, check, write the report
    python ingest/markdown_to_graph.py --dry-run                      also run every write, then roll back
    python ingest/markdown_to_graph.py --load                         write for real (one transaction per fact)

How a file becomes facts (see the plan, section *Ingest*):
- **split**: the file collects independent entries, i.e. it has 2+ `##` sections and each has its own **Added** line.
  Each `##` section becomes a fact.
- **whole**: otherwise. The file is one fact; its `##` headings stay as sections of the statement.
ingest/overrides.json can force a mode per file and change a fact's id, kind, summary or keywords, or skip it.

Each fact: id = slug of its title (permanent; no category), category = the file's leaf category, valid_from = its
**Added** date (else the file's first commit), legacy_updated = **Updated**, context = **Context**, summary = first
sentence, kind guessed from the text, keywords from the index files' Quick Reference, source_refs =
ingest:knowledge/colossus-bets/<file>@<commit>, confidence = legacy_ingest, via = ingest, author ingest@colossusbets.com.
Every write goes through kbwrite (secret scan, integrity before commit). Facts that already exist are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.path.realpath(__file__)).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
import kb  # noqa: E402
import kbwrite  # noqa: E402

SOURCE = ROOT / "knowledge" / "colossus-bets"
OVERRIDES = ROOT / "ingest" / "overrides.json"
INGEST_AUTHOR, INGEST_AUTHOR_NAME = "ingest@colossusbets.com", "Legacy markdown ingest"
LONG_WORDS = 300
LONG_ID = 40          # longer generated ids are flagged so a human picks the permanent name
# Inputs whose uncommitted changes would make the load untraceable to the recorded commit (the report is output).
TRACKED_INPUTS = ("knowledge/colossus-bets", "ingest", "skills/knowledge/scripts", ":(exclude)ingest/report.md")
# The commit the legacy load (#9) read; source_refs point at it. After it, knowledge/ is the graph's export.
LEGACY_COMMIT = "77fc62d11694631db1868ededa976653e0da2a71"
GENERATED_MARK = "<!-- Generated from Colossus KB graph"
META = re.compile(r"^\*\*(Added|Updated|Context)\*\*:\s*(.*?)\s*$")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class Fact:
    file: str                  # relative to knowledge/colossus-bets, e.g. business/pools.md
    title: str
    statement: str
    id: str = ""
    category: str = ""
    kind: str = "description"
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    added: str | None = None
    updated: str | None = None
    context: str | None = None
    flags: list[str] = field(default_factory=list)
    skip: bool = False

    @property
    def words(self) -> int:
        return len(self.statement.split())


# ---------------------------------------------------------------- parsing

def slugify(text: str) -> str:
    """Lower-case kebab slug. Apostrophes are dropped (Event's -> events, pick'em -> pickem). Never truncated:
    long ids are flagged in the report instead, so a person chooses the permanent name."""
    text = text.replace("'", "").replace("\u2019", "")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(preamble lines, [(## heading, body lines)])."""
    pre, secs = [], []
    for line in lines:
        if line.startswith("## "):
            secs.append((line[3:].strip(), []))
        elif secs:
            secs[-1][1].append(line)
        else:
            pre.append(line)
    return pre, secs


def split_meta(lines: list[str]) -> tuple[dict, list[str]]:
    """Pull **Added** / **Updated** / **Context** lines out of a block; return (meta, remaining lines)."""
    meta, rest = {}, []
    for line in lines:
        m = META.match(line.strip())
        if m and m.group(1).lower() not in meta:
            meta[m.group(1).lower()] = m.group(2)
        else:
            rest.append(line)
    return meta, rest


def clean_body(lines: list[str]) -> str:
    """Drop horizontal rules and trim blank lines at both ends; collapse 3+ blank lines."""
    text = "\n".join(line.rstrip() for line in lines if line.strip() != "---")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def file_mode(secs: list[tuple[str, list[str]]]) -> str:
    entries = [body for _, body in secs if any(META.match(line.strip()) and line.strip().startswith("**Added**")
                                              for line in body)]
    return "split" if len(secs) >= 2 and len(entries) == len(secs) else "whole"


def first_sentence(statement: str) -> tuple[str, bool]:
    """Summary candidate and whether it needs a human look."""
    for raw in statement.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "```", ">")):
            continue
        line = re.sub(r"^([-*+]|\d+\.)\s+", "", line)                 # list marker
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)          # links -> text
        line = line.replace("**", "").replace("`", "")
        m = SENTENCE_END.search(line)
        sentence = (m.group(1) if m else line).strip().rstrip(":")
        # "Cause: …", "Who sets it: …", "Observation 1: …" describe a step or a cause, not the rule itself
        labelled = bool(LABEL_PREFIX.match(sentence))
        review = len(sentence) < 20 or len(sentence) > 200 or not m or labelled
        return (sentence[:200].rstrip() + ("…" if len(sentence) > 200 else "")), review
    return "", True


# A sentence ends at . ! or ? followed by a capital (or the end), but not after e.g. / i.e. / etc. / vs.
SENTENCE_END = re.compile(r"^(.+?(?<!\be\.g)(?<!\bi\.e)(?<!\betc)(?<!\bvs)[.!?])(?=\s+[A-Z(\[\"*`]|\s*$)")
LABEL_PREFIX = re.compile(r"^[A-Z][\w ()/'.-]{0,40}:\s")
RULE_WORDS = re.compile(r"\b(must|never|always|do not|don't|should not|shouldn't|only when|required?)\b", re.I)
DECISION_WORDS = re.compile(r"\b(we chose|we decided|decision|decided to|instead of)\b", re.I)


def guess_kind(fact: Fact) -> str:
    text = f"{fact.title}\n{fact.statement}"
    if fact.file.startswith("technical/debugging/") or re.search(r"\b(debug sequence|investigation)\b", text, re.I):
        return "lesson"
    if RULE_WORDS.search(fact.title) or RULE_WORDS.search(fact.summary):
        return "rule"
    if DECISION_WORDS.search(text):
        return "decision"
    if len(RULE_WORDS.findall(fact.statement)) >= 2:
        return "rule"
    if len(re.findall(r"^\s*\d+\.\s", fact.statement, re.M)) >= 3:
        return "procedure"
    return "description"


def parse_file(path: Path, source: Path = SOURCE) -> tuple[str, list[Fact], list[str]]:
    """(mode, facts, notes) for one markdown file."""
    rel = path.relative_to(source).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    pre, secs = sections(lines)
    h1 = next((line[2:].strip() for line in pre if line.startswith("# ")), None)
    mode = file_mode(secs)
    notes, facts = [], []
    if mode == "split":
        intro = clean_body([line for line in pre if not line.startswith("# ")])
        if intro:
            notes.append(f"intro not imported (it's the category description): {intro[:80]!r}")
        for heading, body in secs:
            meta, rest = split_meta(body)
            facts.append(Fact(rel, heading, clean_body(rest), added=meta.get("added"), updated=meta.get("updated"),
                              context=meta.get("context")))
    else:
        meta, rest = split_meta(lines)
        title = h1 or (secs[0][0] if secs else path.stem.replace("-", " "))
        body = [line for line in rest if not (line.startswith("# ") and line[2:].strip() == title)]
        if not h1 and secs and len(secs) == 1:      # a single ## is the title, not a section
            body = [line for line in body if not (line.startswith("## ") and line[3:].strip() == title)]
        facts.append(Fact(rel, title, clean_body(body), added=meta.get("added"), updated=meta.get("updated"),
                          context=meta.get("context")))
    return mode, facts, notes


def quick_reference(source: Path) -> dict[str, list[str]]:
    """file (relative) -> keywords, from every index.md 'Quick Reference' section."""
    out: dict[str, list[str]] = {}
    for index in sorted(source.rglob("index.md")):
        base = index.parent.relative_to(source).as_posix()
        in_qr = False
        for line in index.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                in_qr = line.strip().lower() == "## quick reference"
                continue
            m = re.match(r"^-\s+\**([^:*]+?)\**\s*:\s*([\w./-]+\.md)\b", line) if in_qr else None
            if not m:
                continue
            target = (Path(base) / m.group(2)).as_posix().lstrip("./") if base != "." else m.group(2)
            for kw in re.split(r"\s*/\s*", m.group(1).strip()):
                kw = kw.strip().strip("*").strip()
                if kw and kw.lower() not in [k.lower() for k in out.get(target, [])]:
                    out.setdefault(target, []).append(kw)
    return out


def plan(source: Path = SOURCE, overrides: dict | None = None, first_commit=None) -> tuple[list[Fact], list[dict]]:
    """Parse every entry file into facts and apply overrides. Returns (facts, per-file info)."""
    overrides = overrides or {}
    keywords = quick_reference(source)
    facts, files = [], []
    for path in sorted(p for p in source.rglob("*.md") if p.name != "index.md"):
        rel = path.relative_to(source).as_posix()
        forced = overrides.get("files", {}).get(rel, {}).get("mode")
        mode, parsed, notes = parse_file(path, source)
        if forced and forced != mode:
            notes.append(f"mode forced to {forced} (detected {mode})")
            mode = forced
            if forced == "whole":
                parsed = _as_whole(path, source)
            else:
                parsed = _as_split(path, source)
        file_keywords = keywords.get(rel, [])
        for f in parsed:
            f.category = rel[:-3]
            f.id = slugify(f.title)
            f.summary, review = first_sentence(f.statement)
            if review:
                f.flags.append("summary needs review")
            f.kind = guess_kind(f)
            text = f"{f.title}\n{f.statement}".lower()
            f.keywords = ([k for k in file_keywords if re.search(r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)", text)]
                          if mode == "split" else list(file_keywords))
            if mode == "split" and not f.keywords and len(parsed) == 1:
                f.keywords = list(file_keywords)
            if not f.added:
                f.added = first_commit(path) if first_commit else None
                f.flags.append("no **Added**: first commit date used")
            if f.words > LONG_WORDS:
                f.flags.append(f"{f.words} words: consider splitting")
            o = overrides.get("facts", {}).get(f.id, {})
            for key in ("kind", "summary", "keywords"):
                if key in o:
                    setattr(f, key, o[key])
            if "summary" in o:
                f.flags = [x for x in f.flags if x != "summary needs review"]
            if o.get("skip"):
                f.skip = True
            if "id" in o:
                f.id = o["id"]
            elif len(f.id) > LONG_ID:
                f.flags.append(f"long id ({len(f.id)} chars): choose a shorter permanent id in overrides")
            if not f.statement:
                f.flags.append("empty statement")
            hits = kbwrite.find_secrets({"title": f.title, "summary": f.summary, "statement": f.statement,
                                         "context": f.context, "keywords": f.keywords})
            if hits:
                f.flags.append("SECRET? " + "; ".join(f"{n}: {w}" for n, w in hits))
        if mode == "split":
            used = {k for f in parsed for k in f.keywords}
            unmatched = [k for k in file_keywords if k not in used]
            if unmatched:
                notes.append(f"keywords matching no entry (assign in overrides): {', '.join(unmatched)}")
        facts += parsed
        files.append({"file": rel, "mode": mode, "facts": len(parsed), "notes": notes})
    return facts, files


def _as_whole(path: Path, source: Path = SOURCE) -> list[Fact]:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta, rest = split_meta(lines)
    pre, secs = sections(lines)
    title = next((line[2:].strip() for line in pre if line.startswith("# ")), secs[0][0] if secs else path.stem)
    body = [line for line in rest if not (line.startswith("# ") and line[2:].strip() == title)]
    return [Fact(path.relative_to(source).as_posix(), title, clean_body(body), added=meta.get("added"),
                 updated=meta.get("updated"), context=meta.get("context"))]


def _as_split(path: Path, source: Path = SOURCE) -> list[Fact]:
    _, secs = sections(path.read_text(encoding="utf-8").splitlines())
    out = []
    for heading, body in secs:
        meta, rest = split_meta(body)
        out.append(Fact(path.relative_to(source).as_posix(), heading, clean_body(rest), added=meta.get("added"),
                        updated=meta.get("updated"), context=meta.get("context")))
    return out


def problems(facts: list[Fact]) -> list[str]:
    """Blocking problems: duplicate ids, invalid ids, secrets, empty statements, missing dates."""
    out, seen = [], {}
    for f in facts:
        if f.skip:
            continue
        if not kbwrite.FACT_ID.match(f.id):
            out.append(f"{f.file}: invalid id {f.id!r}")
        if f.id in seen:
            out.append(f"duplicate id {f.id!r}: {seen[f.id]} and {f.file} (set a new id in ingest/overrides.json)")
        seen[f.id] = f.file
        if any(flag.startswith("SECRET?") or flag == "empty statement" for flag in f.flags):
            out.append(f"{f.id}: {', '.join(x for x in f.flags if x.startswith('SECRET?') or x == 'empty statement')}")
        if not f.added or not DATE.match(f.added):
            out.append(f"{f.id}: no usable Added date ({f.added!r})")
        if f.kind not in kbwrite.KINDS:
            out.append(f"{f.id}: kind {f.kind!r} isn't one of {kbwrite.KINDS}")
    return out


# ---------------------------------------------------------------- git and report

def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def source_commit() -> str:
    """The full SHA of HEAD, refusing unless HEAD is on origin/main (so provenance links stay reachable) and the
    ingest inputs have no uncommitted changes."""
    if git("status", "--porcelain", "--", *TRACKED_INPUTS):
        raise kb.KbError("uncommitted changes in knowledge/, ingest/ or skills/knowledge/scripts/; commit them first, "
                         "so every fact traces to the recorded commit")
    git("fetch", "--quiet", "origin", "main")
    head = git("rev-parse", "HEAD")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", head, "origin/main"]).returncode != 0:
        raise kb.KbError(f"HEAD {head[:12]} isn't on origin/main; load from merged main, so source_refs stay reachable")
    return head


def first_commit_date(path: Path) -> str | None:
    out = git("log", "--diff-filter=A", "--follow", "--format=%as", "--", str(path))
    return out.splitlines()[-1] if out else None


def is_generated(source: Path = SOURCE) -> bool:
    """Whether knowledge/ is already the export of the graph (true after #9), i.e. no longer the legacy corpus."""
    return any(p.read_text(encoding="utf-8").startswith(GENERATED_MARK) for p in source.rglob("*.md"))


def legacy_tree(dest: Path, commit: str = LEGACY_COMMIT) -> Path:
    """knowledge/colossus-bets/ as it was at `commit` (the legacy corpus the load read), written under dest."""
    out = dest / "colossus-bets"
    for name in git("ls-tree", "-r", "--name-only", commit, "--", "knowledge/colossus-bets").splitlines():
        if name.endswith(".md"):
            path = out / Path(name).relative_to("knowledge/colossus-bets")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{name}"],
                                            capture_output=True, check=True).stdout)
    return out


def legacy_plan(dest: Path, overrides: dict | None = None) -> tuple[list[Fact], list[dict], Path]:
    """plan() over the legacy corpus at LEGACY_COMMIT, extracted under dest. Returns (facts, files, source folder)."""
    source = legacy_tree(dest)
    facts, files = plan(source, overrides, lambda p: first_commit_date(SOURCE / p.relative_to(source)))
    return facts, files, source


def report(facts: list[Fact], files: list[dict], blocking: list[str]) -> str:
    """Markdown review report: deterministic (no timestamps), so it diffs cleanly in an MR."""
    live = [f for f in facts if not f.skip]
    out = ["# Ingest dry-run report", "",
           "Generated by `python ingest/markdown_to_graph.py --report ingest/report.md`. Review the **ids** (permanent), "
           "**kinds** and flagged **summaries**, then fix them in `ingest/overrides.json` and regenerate.", "",
           f"- Files: {len(files)} ({sum(1 for x in files if x['mode'] == 'split')} split, "
           f"{sum(1 for x in files if x['mode'] == 'whole')} whole)",
           f"- Facts: {len(live)} to load, {len(facts) - len(live)} skipped by overrides",
           f"- Blocking problems: {len(blocking)}", ""]
    if blocking:
        out += ["## Blocking problems", ""] + [f"- {b}" for b in blocking] + [""]
    out += ["## Files", "", "| File | Mode | Facts | Notes |", "|---|---|---|---|"]
    out += [f"| `{x['file']}` | {x['mode']} | {x['facts']} | {'; '.join(x['notes'])} |" for x in files]
    out += ["", "## Facts", "",
            "| id | Category | Kind | Added | Updated | Words | Keywords | Summary | Flags |",
            "|---|---|---|---|---|---|---|---|---|"]
    for f in facts:
        cell = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")
        out.append(f"| `{f.id}`{' (skip)' if f.skip else ''} | `{f.category}` | {f.kind} | {f.added or '-'} | "
                   f"{f.updated or '-'} | {f.words} | {cell(', '.join(f.keywords))} | {cell(f.summary)} | "
                   f"{cell('; '.join(f.flags))} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- loading

def to_input(f: Fact, commit: str, ingested_by: str) -> kbwrite.FactInput:
    def day(value):
        return datetime.fromisoformat(DATE.search(value).group(0)).replace(tzinfo=timezone.utc) if value else None
    extra = {"legacy_updated": day(f.updated)} if f.updated and DATE.search(f.updated) else {}
    return kbwrite.FactInput(
        id=f.id, category=f.category, kind=f.kind, title=f.title, summary=f.summary or f.title, statement=f.statement,
        keywords=f.keywords or None, why=f"Imported from the legacy markdown knowledge base by {ingested_by} (#7)",
        context=f.context, source_type="legacy_ingest",
        source_refs=[f"ingest:knowledge/colossus-bets/{f.file}@{commit}"], confidence=kbwrite.INGEST_CONFIDENCE,
        via=kbwrite.INGEST_VIA, author=INGEST_AUTHOR, author_name=INGEST_AUTHOR_NAME, valid_from=day(f.added),
        extra=extra)


def load_one(tx, f: Fact, commit: str, ingested_by: str, pools_active: bool, now=None) -> dict:
    """Write one fact (skips one that already exists). Returns a status row."""
    if kbwrite.run(tx, ROOT, "fact_exists", id=f.id)[0]["exists"]:
        return {"id": f.id, "status": "exists, skipped"}
    r = kbwrite.write_fact(tx, ROOT, to_input(f, commit, ingested_by), now=now, ingest=True, ingest_active=pools_active)
    return {"id": f.id, "status": r["status"], "version_id": r["version_id"]}


def main(argv: list[str] | None = None) -> int:
    kb.utf8_output()
    ap = argparse.ArgumentParser(prog="markdown_to_graph.py", description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", metavar="FILE", help="parse and check only; write the review report")
    mode.add_argument("--dry-run", action="store_true", help="also run every write against the KB, then roll back")
    mode.add_argument("--load", action="store_true", help="write for real")
    ap.add_argument("--pools-active", action="store_true",
                    help="load business/pools facts as active instead of drafts awaiting approval")
    args = ap.parse_args(argv)

    if is_generated():
        print(f"refusing: knowledge/colossus-bets/ is generated from the graph since #9, not the legacy corpus. The "
              f"legacy load read commit {LEGACY_COMMIT}; its facts are in the graph (see each fact's source_refs).",
              file=sys.stderr)
        return 2
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.is_file() else {}
    facts, files = plan(SOURCE, overrides, first_commit_date)
    blocking = problems(facts)
    if args.report:
        Path(args.report).write_text(report(facts, files, blocking), encoding="utf-8", newline="\n")
        print(f"report: {args.report} ({sum(not f.skip for f in facts)} facts, {len(blocking)} blocking problems)")
        return 1 if blocking else 0
    if blocking:
        print("refusing to load; blocking problems:\n  " + "\n  ".join(blocking), file=sys.stderr)
        return 2
    try:
        commit = source_commit() if args.load else git("rev-parse", "HEAD")
    except kb.KbError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 2
    ingested_by = kb.kb_identity()
    conn = kb.writer_connection()
    results = []
    with kb.driver(conn) as drv, drv.session(database=conn.database) as s:
        for f in (x for x in facts if not x.skip):
            tx = s.begin_transaction()
            try:
                results.append(load_one(tx, f, commit, ingested_by, args.pools_active))
                tx.rollback() if args.dry_run else tx.commit()
            except kb.KbError as e:
                results.append({"id": f.id, "status": f"REFUSED: {e}"})
            finally:
                if not tx.closed():
                    tx.rollback()
    for r in results:
        print(f"{r['id']:<62} {r['status']}")
    refused = [r for r in results if r["status"].startswith("REFUSED")]
    print(f"\n{'DRY RUN (rolled back)' if args.dry_run else 'loaded'}: {len(results) - len(refused)} ok, "
          f"{len(refused)} refused; source commit {commit}; connection {conn.describe()}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
