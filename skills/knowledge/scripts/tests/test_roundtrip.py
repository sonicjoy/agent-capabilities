"""Fidelity of the legacy knowledge through ingest -> graph -> export (#8). No threshold: every line must survive,
except the named, expected changes in ALLOWED_LOSSES. Each step is checked on its own, so a failure says where text
was lost:

- end to end (offline): every content line of every legacy file is in the exported file (as a multiset);
- export / read-back (offline): the ingest parser, run over the export, gives back every fact exactly;
- import (staging, rolled back): the graph holds exactly what the parser produced, so the export from the graph
  equals the export from the parser's plan.
"""
import importlib.util
import json
import re
import sys
from collections import Counter

import pytest

from conftest import ROOT, integration_enabled


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses look the module up while the class is being built
    spec.loader.exec_module(module)
    return module


export = _load("kb_export", "export/graph_to_markdown.py")
ingest = _load("kb_ingest", "ingest/markdown_to_graph.py")
it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")

# Legacy lines the export is expected not to reproduce, with the reason. The test also fails if one of these is
# no longer lost, so the list can't go stale.
ALLOWED_LOSSES = {
    "business/pools.md": {
        "Business rules for tote pools and the engine.":
            "intro of a split file; not a fact. The export shows the category description instead",
    },
    "technical/architecture/rem-units-controller.md": {
        "# RemUnitsController and SEP Behaviour": "H1 of a split file; the export uses the category title",
        "Technical decisions and behaviour for remaining units and match/SEP pools (e.g. MVP).":
            "intro of a split file; not a fact. The export shows the category description instead",
    },
    "technical/workflow/workflow.md": {
        "# Development Workflow": "H1 of a split file; the export uses the category title",
    },
}
HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")
ID_LINE = re.compile(r"^\*\*Id\*\*: `([a-z0-9-]+)`$")
SEED = (r"\{path: '(?P<path>[^']+)', title: (?P<q1>['\"])(?P<title>.*?)(?P=q1), "
        r"description: (?P<q2>['\"])(?P<description>.*?)(?P=q2)\}")


def norm(line: str) -> str:
    """A line's content only: spacing and markdown formatting (heading levels, quote markers, bold, code ticks) don't
    count, so the comparison is about the knowledge, not its layout."""
    m = HEADING.match(line)
    text = m.group(1) if m else line
    text = re.sub(r"^\s*>\s?", "", text).replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def content(lines) -> list[str]:
    return [norm(line) for line in lines if norm(line) and line.strip() != "---"]


def content_lines(text: str) -> Counter:
    return Counter(content(text.splitlines()))


def planned_facts(dest):
    """The parser's plan over the legacy corpus (knowledge/ at ingest.LEGACY_COMMIT; it's generated since #9)."""
    overrides = json.loads((ROOT / "ingest" / "overrides.json").read_text(encoding="utf-8"))
    facts, _, source = ingest.legacy_plan(dest, overrides)
    return [f for f in facts if not f.skip], source


def _day(value):
    m = value and ingest.DATE.search(value)
    return m.group(0) if m else None


def offline_snapshot(facts) -> dict:
    """What the graph would hold after the ingest, built without a database: categories from the 003 seed, facts
    from the parser's plan, mapped as ingest.to_input maps them."""
    seed = (ROOT / "graph" / "migrations" / "003_seed_taxonomy.cypher").read_text(encoding="utf-8")
    library = re.search(r"ON CREATE SET l.title = '([^']+)',\s*l.description = '([^']+)'", seed)
    categories = [{k: m.group(k) for k in ("path", "title", "description")} for m in re.finditer(SEED, seed)]
    assert len(categories) == 30, "the seed regex no longer matches 003_seed_taxonomy.cypher"
    return {"library": export.LIBRARY, "title": library.group(1), "description": library.group(2),
            "categories": categories,
            "facts": [{"id": f.id, "category": f.category, "version_id": f"v-{f.id}", "kind": f.kind, "title": f.title,
                       "summary": f.summary or f.title, "statement": f.statement, "keywords": f.keywords or [],
                       "context": f.context, "added": _day(f.added), "updated": _day(f.updated)} for f in facts]}


@pytest.fixture(scope="module")
def legacy(tmp_path_factory):
    return planned_facts(tmp_path_factory.mktemp("legacy"))


@pytest.fixture(scope="module")
def facts(legacy):
    return legacy[0]


@pytest.fixture(scope="module")
def source(legacy):
    return legacy[1]


@pytest.fixture(scope="module")
def files(facts):
    return export.render(offline_snapshot(facts))


# ---------------------------------------------------------------- offline

def test_every_legacy_file_is_exported(files, source):
    legacy = sorted(p.relative_to(source).as_posix() for p in source.rglob("*.md"))
    assert sorted(files) == legacy


def test_end_to_end_every_legacy_line_survives(files, source):
    """Every non-blank line of each legacy entry file (by content: spacing and formatting ignored) is in its export, as
    often as in the original. Index files are regenerated, so they are checked through keywords instead."""
    lost, unused = {}, {}
    for path in sorted(source.rglob("*.md")):
        rel = path.relative_to(source).as_posix()
        if path.name == "index.md":
            continue
        missing = content_lines(path.read_text(encoding="utf-8")) - content_lines(files[rel])
        allowed = {norm(line) for line in ALLOWED_LOSSES.get(rel, {})}
        if set(missing) - allowed:
            lost[rel] = sorted(set(missing) - allowed)
        if allowed - set(missing):
            unused[rel] = sorted(allowed - set(missing))
    assert not lost, "legacy lines missing from the export:\n" + json.dumps(lost, indent=1, ensure_ascii=False)
    assert not unused, "ALLOWED_LOSSES entries that aren't lost any more:\n" + json.dumps(unused, indent=1)


def test_export_reads_back_as_the_same_facts(tmp_path, facts, files):
    """The ingest parser, run over the export, finds every fact with the same id, category, title, statement,
    dates and context, and every keyword in the regenerated indexes."""
    out = tmp_path / export.LIBRARY
    export.write_tree(out, files)
    back = {}
    for f in ingest.plan(out)[0]:
        lines = f.statement.split("\n")
        ids = [ID_LINE.match(line).group(1) for line in lines if ID_LINE.match(line)]
        assert len(ids) == 1, (f.file, f.title, ids)
        body = [line for line in lines if not ID_LINE.match(line) and line != export.GENERATED_HEADER]
        while body and not body[0].strip():
            body.pop(0)
        if body and body[0].startswith("> "):          # the summary lead line
            body = body[1:]
        back[ids[0]] = (f, body)
    assert sorted(back) == sorted(f.id for f in facts)
    for f in facts:
        g, statement = back[f.id]
        assert (g.category, g.title, g.context, _day(g.added), _day(g.updated)) == (
            f.category, f.title, f.context, _day(f.added), _day(f.updated)), f.id
        assert content(statement) == content(f.statement.split("\n")), f.id
    keywords = ingest.quick_reference(out)
    for f in facts:
        assert set(f.keywords) <= set(keywords.get(f"{f.category}.md", [])), f.id


# ---------------------------------------------------------------- staging, rolled back

INGESTED = """
MATCH (:KbLibrary {name: 'colossus-bets'})<-[:KB_PART_OF]-(c:KbCategory)<-[:KB_IN_CATEGORY]-(f:KbFact)
MATCH (f)-[:KB_HAS_VERSION]->(v:KbFactVersion {via: 'ingest', change_type: 'create'})
RETURN f.id AS id, c.path AS category, v.version_id AS version_id, v.kind AS kind, v.title AS title,
       v.summary AS summary, v.statement AS statement, coalesce(v.keywords, []) AS keywords, v.context AS context,
       v.valid_from AS added, v.legacy_updated AS updated
"""


@it
def test_import_stores_exactly_what_was_parsed(tx, facts, files):
    """The versions the ingest wrote (on an empty staging, written here; on the loaded one, kept in each fact's
    history however it changed since) hold exactly the parser's plan, and render to the same export."""
    for f in facts:
        ingest.load_one(tx, f, "abc1234", "it@colossusbets.com", pools_active=True)
    stored = {}
    for r in tx.run(INGESTED):
        row = r.data()
        row["added"], row["updated"] = export._day(row["added"]), export._day(row["updated"])
        stored[row["id"]] = row
    planned = offline_snapshot(facts)
    by_id = {f["id"]: f for f in planned["facts"]}
    assert sorted(stored) == sorted(by_id)
    fields = ("category", "kind", "title", "summary", "statement", "keywords", "context", "added", "updated")
    diffs = {i: [k for k in fields if stored[i][k] != by_id[i][k]] for i in by_id}
    assert not {i: d for i, d in diffs.items() if d}
    assert export.render({**planned, "facts": list(stored.values())}) == files
