"""Tests for export/graph_to_markdown.py. Integration tests run on KB staging inside rolled-back transactions (KB_IT=1)."""
import importlib.util
import json
import random
import sys
from datetime import datetime, timezone

import pytest

import kb
import kbwrite
from conftest import ROOT, integration_enabled, new_fact


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses look the module up while the class is being built
    spec.loader.exec_module(module)
    return module


export = _load("kb_export", "export/graph_to_markdown.py")
ingest = _load("kb_ingest", "ingest/markdown_to_graph.py")
it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")
H = export.GENERATED_HEADER


def _f(fid, category, title, statement="Body text.", summary="Short summary.", keywords=(), added="2026-01-10",
       updated=None, context=None):
    return {"id": fid, "category": category, "version_id": f"v-{fid}", "kind": "rule", "title": title,
            "summary": summary, "statement": statement, "keywords": list(keywords), "context": context,
            "added": added, "updated": updated}


def snap():
    cats = [("business", "Business", "Business rules."), ("business/glossary", "Glossary", "Terms."),
            ("business/pools", "Pool Rules", "Tote pool rules."), ("technical", "Technical", "Tech | stuff."),
            ("technical/tools", "Tools", "Tool knowledge."), ("technical/tools/gitlab", "GitLab", "Self-hosted.")]
    facts = [
        _f("withdrawals", "business/pools", "Withdrawn units", "Units move to the favourite.\n\n## Edge case\nLate.",
           summary="Units move to the favourite.", keywords=["withdrawals", "favourite"], added="2026-01-23",
           updated="2026-01-28", context="Issue 12"),
        _f("abandoned-leg", "business/pools", "Abandoned future leg", "Nothing changes.", keywords=["abandoned"],
           added="2026-01-26"),
        _f("gitlab-host", "technical/tools/gitlab", "GitLab host", "Use **gitlab.colossusbets.com**.\n\n## Why\nSelf-hosted.",
           summary="Use gitlab.colossusbets.com.", keywords=["GitLab"], added="2026-02-01"),
    ]
    return {"library": "colossus-bets", "title": "Colossus Bets", "description": "Everything.",
            "categories": [{"path": p, "title": t, "description": d} for p, t, d in cats], "facts": facts}


# ---------------------------------------------------------------- unit: no database

@pytest.mark.parametrize("text,top,out", [
    ("## A\ntext\n### B", 3, "### A\ntext\n#### B"),
    ("### A\n## B", 2, "### A\n## B"),                                  # already at the top level: unchanged
    ("plain text", 2, "plain text"),
    ("# A\n```\n# not a heading\n```\n## B", 3, "### A\n```\n# not a heading\n```\n#### B"),
    ("# A\n###### deep", 3, "### A\n###### deep"),                     # capped at h6
])
def test_shift_headings(text, top, out):
    assert export.shift_headings(text, top) == out


def test_render_files_layout_and_header():
    files = export.render(snap())
    assert list(files) == ["business/index.md", "business/pools.md", "index.md", "technical/index.md",
                           "technical/tools/gitlab.md", "technical/tools/index.md"]   # empty glossary: no file
    assert all(text.startswith(H + "\n") and text.endswith("\n") and not text.endswith("\n\n") for text in files.values())


def test_render_leaf_with_several_facts():
    pools = export.render(snap())["business/pools.md"]
    assert pools.index("# Pool Rules\n\nTote pool rules.") < pools.index("## Abandoned future leg") < pools.index(
        "## Withdrawn units")                                            # entries by title
    assert "**Added**: 2026-01-23\n**Updated**: 2026-01-28\n**Context**: Issue 12\n**Id**: `withdrawals`" in pools
    assert "**Added**: 2026-01-26\n**Id**: `abandoned-leg`" in pools   # no Updated, no Context
    assert "### Edge case" in pools and "\n## Edge case" not in pools  # statement headings sit under the entry
    assert "> Short summary." in pools                                  # the statement doesn't open with it
    assert "> Units move" not in pools                                  # ... but this one does: no repeat


def test_render_leaf_with_one_fact_is_the_fact():
    gitlab = export.render(snap())["technical/tools/gitlab.md"]
    assert gitlab.startswith(H + "\n\n# GitLab host\n\n**Added**: 2026-02-01\n**Id**: `gitlab-host`\n\nUse **gitlab")
    assert "\n## Why\nSelf-hosted." in gitlab and "> " not in gitlab          # summary = first sentence: no lead


def test_render_indexes():
    files = export.render(snap())
    root = files["index.md"]
    assert "# Colossus Bets Knowledge Index" in root and "**Last Updated**: 2026-02-01" in root
    assert "- [business/](business/index.md) - Business rules." in root and "## Parent" not in root
    business = files["business/index.md"]
    assert "| [pools.md](pools.md) | Pool Rules | 2026-01-23 | 2026-01-28 | Tote pool rules. |" in business
    assert "glossary" not in business.lower()
    assert "- abandoned: pools.md - Short summary." in business
    assert "- withdrawals / favourite: pools.md - Units move to the favourite." in business
    assert "## Subdirectories\n- [tools/](tools/index.md) - Tool knowledge." in files["technical/index.md"]
    assert "## Parent\n- [../index.md](../index.md)" in files["technical/tools/index.md"]


def test_index_table_cells_are_escaped():
    s = snap()
    s["categories"][2]["description"] = "a | b"
    assert "| a \\| b |" in export.render(s)["business/index.md"]


def test_render_is_deterministic_whatever_the_input_order():
    a = export.render(snap())
    shuffled = snap()
    random.Random(4).shuffle(shuffled["facts"])
    random.Random(5).shuffle(shuffled["categories"])
    assert export.render(shuffled) == a


def test_quick_reference_reads_back_with_the_ingest_parser(tmp_path):
    out = tmp_path / "colossus-bets"
    export.write_tree(out, export.render(snap()))
    assert ingest.quick_reference(out) == {"business/pools.md": ["abandoned", "withdrawals", "favourite"],
                                           "technical/tools/gitlab.md": ["GitLab"]}


def test_write_tree_writes_removes_stale_and_is_idempotent(tmp_path):
    out = tmp_path / "colossus-bets"
    (out / "technical" / "old").mkdir(parents=True)
    (out / "technical" / "old" / "gone.md").write_text("stale", encoding="utf-8")
    (out / "technical" / ".gitkeep").write_text("", encoding="utf-8")
    files = export.render(snap())
    written, removed = export.write_tree(out, files)
    assert written == sorted(files) and removed == ["technical/old/gone.md"]
    assert not (out / "technical" / "old").exists() and (out / "technical" / ".gitkeep").exists()
    assert (out / "business" / "pools.md").read_bytes().count(b"\r") == 0
    assert export.write_tree(out, files) == ([], [])
    assert export.plan_changes(out, files) == ([], [])
    (out / "index.md").write_text("hand edit", encoding="utf-8")
    assert export.plan_changes(out, files) == (["index.md"], [])


def test_write_tree_refuses_mass_removal_before_touching_anything(tmp_path):
    out = tmp_path / "colossus-bets"
    files = export.render(snap())
    export.write_tree(out, files)
    stale = [f"old/gone{i}.md" for i in range(export.MAX_REMOVALS + 1)]
    for p in stale:
        (out / p).parent.mkdir(parents=True, exist_ok=True)
        (out / p).write_text("stale", encoding="utf-8")
    changed = {**files, "index.md": files["index.md"] + "x\n"}
    with pytest.raises(kb.KbError, match=f"would remove {len(stale)} files.*--allow-removals"):
        export.write_tree(out, changed)
    assert all((out / p).exists() for p in stale) and (out / "index.md").read_text(encoding="utf-8") == files["index.md"]
    assert export.write_tree(out, changed, allow_removals=True) == (["index.md"], stale)
    for p in stale[:-1]:                                               # up to MAX_REMOVALS needs no flag
        (out / p).parent.mkdir(parents=True, exist_ok=True)
        (out / p).write_text("stale", encoding="utf-8")
    assert export.write_tree(out, changed)[1] == stale[:-1]


def test_write_tree_only_writes_into_the_library_folder(tmp_path):
    with pytest.raises(kb.KbError, match="must be the 'colossus-bets' folder"):
        export.write_tree(tmp_path / "knowledge", export.render(snap()))


def test_snapshot_refuses_when_integrity_fails(monkeypatch):
    monkeypatch.setattr(kb, "check_problems", lambda tx, checks: [{"check": "multiple_current", "detail": "x"}])
    with pytest.raises(kb.KbError, match="integrity: 1 problem.*nothing exported"):
        export.snapshot(object(), ROOT)


def test_cli_check_reports_differences_without_writing(monkeypatch, tmp_path, capsys):
    out = tmp_path / "colossus-bets"
    monkeypatch.setattr(kb, "reader_connection", lambda: kb.Connection("neo4j+s://x.databases.neo4j.io", "u", "p", "neo4j", "test"))

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_read(self, fn, *a): return snap()

    class _Driver(_Session):
        def session(self, **k): return _Session()

    monkeypatch.setattr(kb, "driver", lambda conn: _Driver())
    assert export.main(["--out", str(out), "--check"]) == 1 and not out.exists()
    assert "differ: business/pools.md" in capsys.readouterr().out
    assert export.main(["--out", str(out)]) == 0
    assert export.main(["--out", str(out), "--check"]) == 0


def test_cli_refuses_to_overwrite_from_an_empty_graph(monkeypatch, tmp_path, capsys):
    out = tmp_path / "colossus-bets"
    out.mkdir()
    (out / "index.md").write_text("kept", encoding="utf-8")
    empty = {**snap(), "facts": []}
    monkeypatch.setattr(kb, "reader_connection", lambda: kb.Connection("neo4j+s://x.databases.neo4j.io", "u", "p", "neo4j", "test"))

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_read(self, fn, *a): return empty
        def session(self, **k): return self

    monkeypatch.setattr(kb, "driver", lambda conn: _Session())
    assert export.main(["--out", str(out)]) == 2
    assert "no current facts" in capsys.readouterr().err and (out / "index.md").read_text(encoding="utf-8") == "kept"


def test_kb_py_export_runs_the_checkout_exporter(monkeypatch, tmp_path, capsys):
    (tmp_path / "export").mkdir()
    (tmp_path / "export" / "graph_to_markdown.py").write_text(
        "import json, kb\n"
        "def main(argv, root):\n"
        "    (root / 'seen.json').write_text(json.dumps(argv))\n"
        "    raise kb.KbError('stub refused')\n", encoding="utf-8")
    monkeypatch.setenv("COLOSSUS_KB_REPO", str(tmp_path))
    assert kb.main(["export", "--check", "--out", "x/colossus-bets"]) == 2       # the exporter's KbError is kb.py's
    assert "kb.py: stub refused" in capsys.readouterr().err
    assert json.loads((tmp_path / "seen.json").read_text(encoding="utf-8")) == ["--out", "x/colossus-bets", "--check"]
    kb.main(["export", "--allow-removals"])
    assert json.loads((tmp_path / "seen.json").read_text(encoding="utf-8")) == ["--allow-removals"]


# ---------------------------------------------------------------- integration: staging, rolled back

def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@it
def test_export_of_the_ingested_corpus(tx, tmp_path):
    overrides = json.loads((ROOT / "ingest" / "overrides.json").read_text(encoding="utf-8"))
    planned, _, source = ingest.legacy_plan(tmp_path, overrides)
    facts = [f for f in planned if not f.skip]
    for f in facts:
        ingest.load_one(tx, f, "abc1234", "it@colossusbets.com", pools_active=True)
    files = export.render(export.snapshot(tx))
    assert files == export.render(export.snapshot(tx))
    legacy = sorted(p.relative_to(source).as_posix() for p in source.rglob("*.md"))
    assert sorted(files) == legacy                                    # the same 30 files as the legacy corpus
    for f in facts:
        hits = [p for p, text in files.items() if f"**Id**: `{f.id}`" in text]
        assert hits == [f"{f.category}.md"], f.id


@it
def test_export_dates_follow_the_versions(tx):
    def write(now, **kw):
        base = dict(id="it-x", why="test", source_type="test", source_refs=["kb/8"], author="it-x@colossusbets.com",
                    via="agent", category="technical/conventions/code-quality", kind="rule", title="Export dates",
                    summary="Dates follow versions.", statement="Dates follow versions.")
        return kbwrite.write_fact(tx, ROOT, kbwrite.FactInput(**{**base, **kw}), now=now)["version_id"]

    def dates():
        return next((f["added"], f["updated"]) for f in export.snapshot(tx)["facts"] if f["id"] == "it-x")

    v1 = write(utc(2026, 1, 10), valid_from=utc(2026, 1, 10))
    assert dates() == ("2026-01-10", None)
    v2 = write(utc(2026, 2, 2), statement="Dates follow versions, corrected.", change_type="correction",
               valid_from=utc(2026, 2, 1), expected_current=v1)
    assert dates() == ("2026-02-01", "2026-02-02")                   # the wrong start no longer counts
    write(utc(2026, 3, 2), statement="Dates follow versions, v3.", valid_from=utc(2026, 3, 1), expected_current=v2)
    assert dates() == ("2026-02-01", "2026-03-02")                   # Added stays; Updated = when recorded


@it
def test_a_never_valid_version_does_not_set_added(tx):
    base = dict(id="it-nv", why="test", source_type="test", source_refs=["kb/8"], author="it-x@colossusbets.com",
                via="agent", category="technical/conventions/code-quality", kind="rule", title="Never valid",
                summary="Started by mistake.", statement="Started by mistake.")
    v1 = kbwrite.write_fact(tx, ROOT, kbwrite.FactInput(**base, valid_from=utc(2026, 1, 1)),
                            now=utc(2026, 1, 2))["version_id"]
    kbwrite.retract(tx, ROOT, "it-nv", "never applied", ["kb/8"], "it-x@colossusbets.com", v1, never_valid=True,
                    now=utc(2026, 1, 3))
    kbwrite.write_fact(tx, ROOT, kbwrite.FactInput(**{**base, "statement": "Really from March."},
                                                   valid_from=utc(2026, 3, 1), expected_current=v1), now=utc(2026, 3, 2))
    f = next(f for f in export.snapshot(tx)["facts"] if f["id"] == "it-nv")
    assert (f["added"], f["updated"]) == ("2026-03-01", "2026-03-02")


@it
def test_export_refuses_a_graph_that_fails_integrity(tx):
    new_fact(tx, "it-no-versions", category="technical/conventions/code-quality")
    with pytest.raises(kb.KbError, match="fact_without_versions"):
        export.snapshot(tx)
