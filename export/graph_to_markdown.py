#!/usr/bin/env python3
"""Regenerate knowledge/colossus-bets/ from the graph's current versions (#8).

    python export/graph_to_markdown.py [--out knowledge/colossus-bets]      write the files
    python export/graph_to_markdown.py --check                              compare only; exit 1 if anything differs
    kb.py export [--out DIR] [--check] [--allow-removals]                   the same, through kb.py

Layout (see the plan, section *Export*):
- one file per leaf category that has current facts (`<path>.md`), entries ordered by title. A leaf with one fact is
  that fact (H1 = its title); a leaf with several has the category title as H1 and one `##` entry per fact;
- an `index.md` per folder (and the library root) with its files, subfolders and a Quick Reference of keywords;
- every file starts with GENERATED_HEADER. Drafts and retracted facts are not exported.

The integrity checks and the read run in one read transaction (one snapshot); any problem means nothing is written.
The output depends only on the graph (no timestamps), so two runs on the same graph give identical files. Markdown
files under the output folder that the export no longer produces are removed; other files (e.g. .gitkeep) are kept.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.path.realpath(__file__)).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
import kb  # noqa: E402

LIBRARY = "colossus-bets"
DEFAULT_OUT = ROOT / "knowledge" / LIBRARY
GENERATED_HEADER = "<!-- Generated from Colossus KB graph; edit via kb.py, not here -->"
MAX_REMOVALS = 3      # more stale files than this needs --allow-removals (retiring a category removes 1-2)


# ---------------------------------------------------------------- reading

def snapshot(tx, root: Path = ROOT, library: str = LIBRARY) -> dict:
    """Categories and current facts of one library, refusing if any integrity check fails. Call it inside one
    transaction, so the checks and the read see the same graph."""
    problems = kb.check_problems(tx, kb.integrity_checks(root))
    if problems:
        listed = "; ".join(f"{p['check']}: {p['detail']}" for p in problems[:5])
        raise kb.KbError(f"integrity: {len(problems)} problem(s), nothing exported ({listed}); run kb.py integrity")
    categories = kb.read_rows(tx, root, "export_categories", library=library)
    if not categories:
        raise kb.KbError(f"no library {library!r} (or it has no categories)")
    facts = kb.read_rows(tx, root, "export_facts", library=library)
    for f in facts:
        f["added"], f["updated"] = _day(f["added"]), _day(f["updated"])
    return {"library": library, "title": categories[0]["library_title"],
            "description": categories[0]["library_description"],
            "categories": [{k: c[k] for k in ("path", "title", "description")} for c in categories], "facts": facts}


def _day(value) -> str | None:
    return kb._date(value) if value is not None else None


# ---------------------------------------------------------------- rendering

shift_headings = kb.shift_headings


def _meta(f: dict) -> list[str]:
    out = [f"**Added**: {f['added']}"]
    if f.get("updated"):
        out.append(f"**Updated**: {f['updated']}")
    if f.get("context"):
        out.append(f"**Context**: {f['context']}")
    out.append(f"**Id**: `{f['id']}`")
    return out


def _plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text).replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _body(f: dict, top: int) -> list[str]:
    """The summary as a lead line (unless the statement already opens with it), then the statement."""
    statement = "\n".join(line.rstrip() for line in f["statement"].strip().split("\n"))
    lead = _plain(f["summary"]).rstrip(".")
    if lead and _plain(statement).startswith(lead):
        return ["", shift_headings(statement, top)]
    return ["", f"> {f['summary']}", "", shift_headings(statement, top)]


def render_leaf(category: dict, facts: list[dict]) -> str:
    if len(facts) == 1:
        f = facts[0]
        lines = [GENERATED_HEADER, "", f"# {f['title']}", "", *_meta(f), *_body(f, 2)]
    else:
        lines = [GENERATED_HEADER, "", f"# {category['title']}", ""]
        if category.get("description"):
            lines += [category["description"], ""]
        for f in facts:
            lines += ["---", "", f"## {f['title']}", *_meta(f), *_body(f, 3), ""]
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def _cell(text: str | None) -> str:
    return (text or "-").replace("|", "\\|").replace("\n", " ")


def _child(path: str, parent: str) -> bool:
    """`path` is a direct child of `parent` ('' = the library root)."""
    rest = path[len(parent) + 1:] if parent else path
    return (path.startswith(parent + "/") or not parent) and rest != "" and "/" not in rest


def render_index(path: str, title: str, description: str | None, leaves: list[dict], folders: list[dict],
                 by_category: dict[str, list[dict]], last_updated: str | None, is_root: bool) -> str:
    lines = [GENERATED_HEADER, "", f"# {title} Knowledge Index", ""]
    if description:
        lines += [description, ""]
    if last_updated:
        lines += [f"**Last Updated**: {last_updated}", ""]
    if is_root:
        lines += ["**Snapshot, not kept up to date.** Agents read the Colossus KB graph with `kb.py`, not these files (#19).", "",
                  "Generated from the Colossus KB graph by `kb.py export`. Change knowledge with `kb.py write` "
                  "(see the knowledge skill); never edit these files by hand.", ""]
    if leaves:
        lines += ["## Files in This Directory", "| File | Title | Added | Updated | Description |",
                  "|------|-------|-------|---------|-------------|"]
        for c in leaves:
            facts = by_category[c["path"]]
            name = c["path"].rsplit("/", 1)[-1] + ".md"
            updated = max((f["updated"] for f in facts if f["updated"]), default=None)
            lines.append(f"| [{name}]({name}) | {_cell(c['title'])} | {min(f['added'] for f in facts)} | "
                         f"{updated or '-'} | {_cell(c['description'])} |")
        lines.append("")
    if folders:
        lines.append("## Subdirectories")
        for c in folders:
            name = c["path"].rsplit("/", 1)[-1]
            lines.append(f"- [{name}/]({name}/index.md) - {c['description'] or c['title']}")
        lines.append("")
    refs = []      # one line per fact that has keywords: "- kw1 / kw2: file.md - summary"
    for c in leaves:
        name = c["path"].rsplit("/", 1)[-1] + ".md"
        refs += [f"- {' / '.join(f['keywords'])}: {name} - {f['summary']}"
                 for f in by_category[c["path"]] if f["keywords"]]
    if refs:
        lines += ["## Quick Reference", *refs, ""]
    if not is_root:
        lines += ["## Parent", "- [../index.md](../index.md)", ""]
    return "\n".join(lines).rstrip() + "\n"


def render(snap: dict) -> dict[str, str]:
    """Relative path (posix) -> file content, for the whole library."""
    categories = {c["path"]: c for c in snap["categories"]}
    by_category: dict[str, list[dict]] = {}
    for f in sorted(snap["facts"], key=lambda f: (f["category"], f["title"].lower(), f["id"])):
        by_category.setdefault(f["category"], []).append(f)
    paths = sorted(categories)
    is_leaf = {p: not any(q.startswith(p + "/") for q in paths) for p in paths}

    def has_content(p: str) -> bool:
        return any(c == p or c.startswith(p + "/") for c in by_category)

    def dates(p: str) -> list[str]:
        return [f["updated"] or f["added"] for c, fs in by_category.items() if c == p or c.startswith(p + "/") or not p
                for f in fs]

    files: dict[str, str] = {}
    for p in paths:
        if is_leaf[p] and p in by_category:
            files[f"{p}.md"] = render_leaf(categories[p], by_category[p])
    for p in [""] + [p for p in paths if not is_leaf[p] and has_content(p)]:
        children = [categories[q] for q in paths if _child(q, p) and has_content(q)]
        leaves = [c for c in children if is_leaf[c["path"]]]
        folders = [c for c in children if not is_leaf[c["path"]]]
        title, description = (snap["title"], snap["description"]) if not p else (categories[p]["title"],
                                                                                  categories[p]["description"])
        files[f"{p}/index.md" if p else "index.md"] = render_index(
            p, title, description, leaves, folders, by_category, max(dates(p), default=None), is_root=not p)
    return dict(sorted(files.items()))


# ---------------------------------------------------------------- writing

def plan_changes(out: Path, files: dict[str, str]) -> tuple[list[str], list[str]]:
    """(paths to write: new or different, stale markdown paths to remove), relative and sorted."""
    write = [p for p, text in files.items()
             if not (out / p).is_file() or (out / p).read_text(encoding="utf-8") != text]
    existing = sorted(q.relative_to(out).as_posix() for q in out.rglob("*.md")) if out.is_dir() else []
    return write, [p for p in existing if p not in files]


def write_tree(out: Path, files: dict[str, str], library: str = LIBRARY,
               allow_removals: bool = False) -> tuple[list[str], list[str]]:
    """Write `files` under `out` and remove stale markdown. Refuses unless the folder is named after the library, and
    (before touching anything) when more than MAX_REMOVALS files would go, unless allow_removals: a partial graph
    (a test database, a half-finished load) would otherwise quietly delete most of the export."""
    if out.name != library:
        raise kb.KbError(f"--out must be the {library!r} folder (got {out}); the export removes stale .md files there")
    write, remove = plan_changes(out, files)
    if len(remove) > MAX_REMOVALS and not allow_removals:
        raise kb.KbError(f"the export would remove {len(remove)} files (more than {MAX_REMOVALS}), e.g. "
                         f"{', '.join(remove[:3])}; is this the right database? Check with --check, then re-run with "
                         f"--allow-removals if it's intended")
    for p in write:
        (out / p).parent.mkdir(parents=True, exist_ok=True)
        (out / p).write_text(files[p], encoding="utf-8", newline="\n")
    for p in remove:
        (out / p).unlink()
    for d in sorted((d for d in out.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return write, remove


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    kb.utf8_output()
    ap = argparse.ArgumentParser(prog="graph_to_markdown.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default: knowledge/{LIBRARY}")
    ap.add_argument("--check", action="store_true", help="compare only; exit 1 if the files differ from the graph")
    ap.add_argument("--allow-removals", action="store_true",
                    help=f"allow removing more than {MAX_REMOVALS} stale files (check with --check first)")
    args = ap.parse_args(argv)
    try:
        conn = kb.reader_connection()
        with kb.driver(conn) as drv, drv.session(database=conn.database) as s:
            snap = s.execute_read(snapshot, root, LIBRARY)
        files = render(snap)
        out = args.out.resolve()
        if args.check:
            write, remove = plan_changes(out, files)
        elif not snap["facts"]:      # an empty or wrong database would otherwise delete the whole export
            raise kb.KbError(f"no current facts in {conn.describe()}; refusing to overwrite {out}")
        else:
            write, remove = write_tree(out, files, allow_removals=args.allow_removals)
    except kb.KbError as e:
        print(f"export: {e}", file=sys.stderr)
        return 2
    verb = ("differ", "stale") if args.check else ("written", "removed")
    for p in write:
        print(f"  {verb[0]}: {p}")
    for p in remove:
        print(f"  {verb[1]}: {p}")
    print(f"export{' --check' if args.check else ''}: {len(snap['facts'])} facts, {len(files)} files; "
          f"{len(write)} {verb[0]}, {len(remove)} {verb[1]}; connection {conn.describe()}")
    return 1 if args.check and (write or remove) else 0


if __name__ == "__main__":
    sys.exit(main())
