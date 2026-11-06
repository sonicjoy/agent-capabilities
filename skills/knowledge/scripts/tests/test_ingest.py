"""Tests for ingest/markdown_to_graph.py. Unit tests use a temporary markdown tree; integration tests load into KB
staging inside rolled-back transactions (KB_IT=1)."""
import importlib.util
import json
import sys
from datetime import datetime, timezone

import pytest

import kb
import kbwrite
from conftest import ROOT, integration_enabled

_spec = importlib.util.spec_from_file_location("kb_ingest", ROOT / "ingest" / "markdown_to_graph.py")
ingest = importlib.util.module_from_spec(_spec)
sys.modules["kb_ingest"] = ingest          # dataclasses look the module up while the class is being built
_spec.loader.exec_module(ingest)
it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")

SPLIT = """# Pool Business Rules

Business rules for tote pools.

---

## Withdrawn Runner Re-allocation
**Added**: 2026-01-23
**Updated**: 2026-01-28
**Context**: Pool 123 incident.

When a runner is withdrawn, their units must be moved to the favourite (e.g. the shortest price). More detail on withdrawals.

---

## Started Event Order
**Added**: 2026-01-26

STARTED events must be the first events chronologically.
"""
WHOLE = """# StatsFeedDaemon – stats and cbtote updates

**Added**: 2026-01-27
**Context**: Clarifying how stats reach cbtote.

## Overview

StatsFeedDaemon is a separate process. It reads SportsData.

## ID mapping

- one
- two
"""
SINGLE = """## Fix Duplicated Data Using SQL Scripts

**Added**: 2026-03-05

When duplicated data causes runtime errors, fix it at source with SQL scripts.
"""
INDEX = """# Index

## Quick Reference
- withdrawals: pools.md - withdrawn runners
- **SEP**: pools.md - single event pools
- pool restart / started event: pools.md - ordering
"""


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "colossus-bets"
    (src / "business").mkdir(parents=True)
    (src / "technical" / "conventions").mkdir(parents=True)
    (src / "business" / "pools.md").write_text(SPLIT, encoding="utf-8")
    (src / "business" / "index.md").write_text(INDEX, encoding="utf-8")
    (src / "technical" / "statsfeed.md").write_text(WHOLE, encoding="utf-8")
    (src / "technical" / "conventions" / "data-fixes.md").write_text(SINGLE, encoding="utf-8")
    return src


def by_id(facts):
    return {f.id: f for f in facts}


# ---------------------------------------------------------------- parsing

def test_modes_titles_and_metadata(tree):
    facts, files = ingest.plan(tree)
    modes = {x["file"]: x["mode"] for x in files}
    assert modes == {"business/pools.md": "split", "technical/statsfeed.md": "whole",
                     "technical/conventions/data-fixes.md": "whole"}
    f = by_id(facts)
    w = f["withdrawn-runner-re-allocation"]
    assert (w.category, w.added, w.updated, w.context) == ("business/pools", "2026-01-23", "2026-01-28", "Pool 123 incident.")
    assert "**Added**" not in w.statement and "---" not in w.statement
    s = f["statsfeeddaemon-stats-and-cbtote-updates"]
    assert s.statement.startswith("## Overview") and "## ID mapping" in s.statement   # sections kept
    d = f["fix-duplicated-data-using-sql-scripts"]
    assert d.title == "Fix Duplicated Data Using SQL Scripts" and not d.statement.startswith("##")
    assert "intro not imported" in files[0]["notes"][0]


def test_summary_kind_and_keywords(tree):
    f = by_id(ingest.plan(tree)[0])
    w = f["withdrawn-runner-re-allocation"]
    assert w.summary == "When a runner is withdrawn, their units must be moved to the favourite (e.g. the shortest price)."
    assert w.kind == "rule" and w.keywords == ["withdrawals"]          # keyword matched in this entry's text
    st = f["started-event-order"]
    assert st.kind == "rule" and st.keywords == ["started event"]      # 'SEP' doesn't match inside other words
    assert f["statsfeeddaemon-stats-and-cbtote-updates"].summary == "StatsFeedDaemon is a separate process."


def test_unmatched_split_keywords_are_reported(tree):
    files = ingest.plan(tree)[1]
    assert "keywords matching no entry (assign in overrides): SEP, pool restart" in files[0]["notes"]


@pytest.mark.parametrize("title,slug", [
    ("MVP: Remaining Units When All Sport Events Terminal (Issue #151)", "mvp-remaining-units-when-all-sport-events-terminal-issue-151"),
    ("StatsFeedDaemon – stats and cbtote updates", "statsfeeddaemon-stats-and-cbtote-updates"),
    ("Ünïcode ↔ Ärger", "unicode-arger"),
    ("Use Market Status from Event's MarketHistories", "use-market-status-from-events-markethistories"),
    ("Fantasy / Mido pick’em images", "fantasy-mido-pickem-images"),
    ("x" * 30 + " " + "y" * 40, "x" * 30 + "-" + "y" * 40),                 # never truncated
])
def test_slugify(title, slug):
    assert ingest.slugify(title) == slug


@pytest.mark.parametrize("text,summary,review", [
    ("Plain sentence here. Second one.", "Plain sentence here.", False),
    ("Uses market_metrics (e.g. MVP) as the source. More.", "Uses market_metrics (e.g. MVP) as the source.", False),
    ("- **Bold** list item that is long enough.", "Bold list item that is long enough.", False),
    ("When making code changes:\n1. build", "When making code changes", True),
    ("| table | row |\nText after the table, long enough.", "Text after the table, long enough.", False),
    ("**Cause**: GetPoolAsync was reloading the pool on every message.", "Cause: GetPoolAsync was reloading the pool on every message.", True),
    ("Who sets it: The console sets the flag on restart.", "Who sets it: The console sets the flag on restart.", True),
])
def test_first_sentence(text, summary, review):
    assert ingest.first_sentence(text) == (summary, review)


def test_summary_override_clears_the_review_flag(tree):
    (tree / "technical" / "cause.md").write_text(
        "# Cause Note\n\n**Added**: 2026-01-01\n\nCause: something happened here.\n", encoding="utf-8")
    flagged = by_id(ingest.plan(tree)[0])["cause-note"]
    assert "summary needs review" in flagged.flags
    fixed = by_id(ingest.plan(tree, {"facts": {"cause-note": {"summary": "Something happened."}}})[0])["cause-note"]
    assert fixed.summary == "Something happened." and "summary needs review" not in fixed.flags


def test_overrides_change_mode_id_kind_and_skip(tree):
    overrides = {"files": {"business/pools.md": {"mode": "whole"}},
                 "facts": {"fix-duplicated-data-using-sql-scripts": {"id": "data-fixes-sql", "kind": "rule"},
                           "statsfeeddaemon-stats-and-cbtote-updates": {"skip": True}}}
    facts, files = ingest.plan(tree, overrides)
    f = by_id(facts)
    assert "pool-business-rules" in f and "mode forced to whole" in files[0]["notes"][-1]
    assert f["data-fixes-sql"].kind == "rule"
    assert f["statsfeeddaemon-stats-and-cbtote-updates"].skip


def test_blocking_problems_duplicates_and_secrets(tree):
    (tree / "technical" / "copy.md").write_text(SINGLE.replace("SQL scripts.", "SQL scripts. password=hunter2222"),
                                                 encoding="utf-8")
    problems = ingest.problems(ingest.plan(tree)[0])
    assert any("duplicate id 'fix-duplicated-data-using-sql-scripts'" in p for p in problems)
    assert any("SECRET?" in p and "hunter2222" not in p for p in problems)


def test_long_ids_are_flagged_not_cut(tree):
    (tree / "technical" / "long.md").write_text(
        "# Deleting Unnecessary Code Is More Productive Than Writing New\n\n**Added**: 2026-02-04\n\nText long enough here.\n",
        encoding="utf-8")
    f = by_id(ingest.plan(tree)[0])["deleting-unnecessary-code-is-more-productive-than-writing-new"]
    assert f"long id ({len(f.id)} chars): choose a shorter permanent id in overrides" in f.flags
    renamed = by_id(ingest.plan(tree, {"facts": {f.id: {"id": "delete-over-add"}}})[0])["delete-over-add"]
    assert not any(flag.startswith("long id") for flag in renamed.flags)


def test_load_refuses_untraceable_sources(monkeypatch):
    calls = []
    monkeypatch.setattr(ingest, "git", lambda *a: calls.append(a) or (" M ingest/overrides.json" if a[0] == "status" else "x"))
    with pytest.raises(kb.KbError, match="uncommitted changes"):
        ingest.source_commit()
    assert calls[0][:2] == ("status", "--porcelain") and ":(exclude)ingest/report.md" in calls[0]
    monkeypatch.setattr(ingest, "git", lambda *a: "" if a[0] in ("status", "fetch") else "f" * 40)
    monkeypatch.setattr(ingest.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1})())
    with pytest.raises(kb.KbError, match="isn't on origin/main"):
        ingest.source_commit()


def test_missing_added_uses_first_commit(tree):
    (tree / "technical" / "nodate.md").write_text("# No Date Here\n\nSome text that is long enough.\n", encoding="utf-8")
    f = by_id(ingest.plan(tree, first_commit=lambda p: "2026-01-02")[0])["no-date-here"]
    assert f.added == "2026-01-02" and "first commit" in f.flags[0]


def test_report_is_deterministic_and_lists_every_fact(tree):
    facts, files = ingest.plan(tree)
    a, b = ingest.report(facts, files, []), ingest.report(*ingest.plan(tree), [])
    assert a == b and a.count("\n| `") == len(facts) + len(files)


def test_real_corpus_plans_cleanly(tmp_path):
    overrides = json.loads((ROOT / "ingest" / "overrides.json").read_text(encoding="utf-8"))
    facts, files, _ = ingest.legacy_plan(tmp_path, overrides)
    assert len(files) == 21 and ingest.problems(facts) == []
    assert len({f.id for f in facts}) == len(facts) == 46


def test_cli_write_cannot_use_the_ingest_path():
    inp = kbwrite.FactInput(id="it-x", why="w", source_type="t", source_refs=["x"], author="a@b.co", via="ingest",
                            category="technical/conventions/code-quality", kind="rule", title="T", summary="S",
                            statement="B")
    with pytest.raises(kb.KbError, match="--via"):
        kbwrite.write_fact(None, ROOT, inp)


# ---------------------------------------------------------------- integration: load in a rolled-back transaction

def _fact(**kw):
    base = dict(file="technical/conventions/code-quality.md", title="Delete over add", statement="Prefer deleting code.",
                category="technical/conventions/code-quality", id="it-ingest-delete", kind="rule",
                summary="Prefer deleting code.", keywords=["delete over add"], added="2026-02-04",
                updated="2026-02-10", context="Refactoring session.")
    base.update(kw)
    return ingest.Fact(**base)


@it
def test_load_one_writes_a_legacy_version_and_skips_existing(tx):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    r = ingest.load_one(tx, _fact(), "abc1234", "joe.luo@colossusbets.com", pools_active=False, now=now)
    assert r["status"] == "active"
    row = kb.read_fact(tx, ROOT, "it-ingest-delete")
    v = row["version"]
    assert (v["confidence"], v["via"], v["source_type"]) == ("legacy_ingest", "ingest", "legacy_ingest")
    assert v["source_refs"] == ["ingest:knowledge/colossus-bets/technical/conventions/code-quality.md@abc1234"]
    assert v["valid_from"].iso_format().startswith("2026-02-04") and row["author"] == "ingest@colossusbets.com"
    assert "joe.luo@colossusbets.com" in v["why"] and v["context"] == "Refactoring session."
    legacy = tx.run("MATCH (v:KbCurrent {version_id: $vid}) RETURN v.legacy_updated AS u", vid=r["version_id"]).single()["u"]
    assert legacy.iso_format().startswith("2026-02-10")
    assert ingest.load_one(tx, _fact(), "abc1234", "x@y.co", pools_active=False, now=now)["status"] == "exists, skipped"


@it
def test_pools_facts_are_drafts_unless_pools_active(tx):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    pools = dict(file="business/pools.md", category="business/pools")
    assert ingest.load_one(tx, _fact(id="it-pool-a", **pools), "c", "j@c.co", pools_active=False, now=now)["status"] == "draft"
    assert ingest.load_one(tx, _fact(id="it-pool-b", **pools), "c", "j@c.co", pools_active=True, now=now)["status"] == "active"


def test_ingest_refuses_the_generated_knowledge_folder(tmp_path, capsys):
    """Since #9, knowledge/ is the graph's export; the legacy corpus lives at LEGACY_COMMIT."""
    assert ingest.is_generated()
    assert ingest.main(["--report", str(tmp_path / "r.md")]) == 2 and not (tmp_path / "r.md").exists()
    assert ingest.LEGACY_COMMIT in capsys.readouterr().err
    assert not ingest.is_generated(ingest.legacy_tree(tmp_path))
