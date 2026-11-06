"""Tests for `kb.py read`. Unit tests need no database; the history scenario runs on KB staging in a rolled-back
transaction (KB_IT=1)."""
import json
import re
from datetime import datetime, timezone

import pytest

import kb
from conftest import ROOT, add_version, integration_enabled, new_fact, supersede, it_search

it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")
READ_TEMPLATES = ["categories", "current_by_category", "search", "fact", "fact_as_of", "fact_kb_as_of", "related",
                  "history", "export_categories", "export_facts", "context"]


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ---------------------------------------------------------------- unit: no database

@pytest.mark.parametrize("name", READ_TEMPLATES)
def test_read_templates_are_single_read_only_kb_statements(name):
    query = kb.load_template(ROOT, "read", name)
    code = re.sub(r"//[^\n]*", "", query)
    assert not re.search(r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DETACH|CALL)\b", code), f"{name} must be read-only"
    assert all(label.startswith("Kb") for label in re.findall(r"\(\w*:(\w+)", code)), name
    assert all(rel.startswith("KB_") for rel in re.findall(r"\[\w*:(\w+)", code)), name
    assert "$" in code, f"{name} must take parameters"


@pytest.mark.parametrize("q,expected", [
    ("Pool restarts", [["pool"], ["restarts", "restart"]]),
    ("settlement of the MVP", [["settlement", "settle"], ["mvp"]]),   # 'of' too short, 'the' a stopword
    ("a b pools pools", [["pools", "pool"]]),                          # short words dropped, duplicates removed
    ("bus fees", [["bus"], ["fees"]]),                                 # no stem when fewer than 4 characters remain
    ("histories", [["histories", "history"]]),
    ("Ünïcode SETTLED", [["ünïcode"], ["settled", "settl"]]),
    ("leg-per-event RU", [["leg"], ["event"], ["ru"]]),                # 'per' stopword; 'ru' a known short word
    ("pool status", [["pool"], ["status", "statu"]]),
])
def test_search_words(q, expected):
    assert kb.search_words(q) == expected


def test_search_words_are_capped():
    assert len(kb.search_words(" ".join(f"word{i}" for i in range(40)))) == kb.MAX_WORDS


@pytest.mark.parametrize("value,expected", [
    ("2026-03-01", utc(2026, 3, 1)),                                   # a date is midnight UTC
    ("2026-03-01T12:00:00Z", utc(2026, 3, 1, 12)),
    ("2026-03-01T12:00:00", utc(2026, 3, 1, 12)),                      # no time zone: taken as UTC
    ("2026-03-01T12:00:00+01:00", utc(2026, 3, 1, 11)),
])
def test_parse_instant_returns_aware_datetimes(value, expected):
    parsed = kb.parse_instant(value)
    assert parsed.tzinfo is not None and parsed == expected


@pytest.mark.parametrize("value", ["2026-13-01", "yesterday", ""])
def test_parse_instant_rejects(value):
    with pytest.raises(kb.KbError):
        kb.parse_instant(value)


class RecordingTx:
    def __init__(self):
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return []


def test_limits_are_capped_and_prefix_normalised():
    tx = RecordingTx()
    kb.read_search(tx, ROOT, "pool", limit=50)
    kb.read_current_by_category(tx, ROOT, "/business/pools/", limit=10_000)
    kb.read_context(tx, ROOT, "/technical/workflow/", limit=0)
    assert tx.calls[0][1] == {"words": [["pool"]], "limit": kb.SEARCH_LIMIT_MAX}
    assert tx.calls[1][1] == {"path_prefix": "business/pools", "limit": kb.CATEGORY_LIMIT_MAX}
    assert tx.calls[2][1] == {"path_prefix": "technical/workflow", "limit": 1}


@pytest.mark.parametrize("prefix", ["", "/", "//"])
def test_context_refuses_the_whole_library(prefix):
    with pytest.raises(kb.KbError, match="needs a category"):
        kb.read_context(RecordingTx(), ROOT, prefix)


def test_format_context_gives_full_statements_under_their_own_headings():
    rows = [{"id": "qa-process", "title": "QA process", "kind": "procedure", "summary": "Two paths.",
             "statement": "# Path 1\nEpic from QA.\n```\n# not a heading\n```"}]
    text = kb.format_context("/technical/workflow/", rows)
    assert text.startswith("# Colossus KB: technical/workflow\n")
    assert "## QA process\n`qa-process` (procedure). Two paths.\n\n### Path 1\nEpic from QA." in text
    assert "# not a heading" in text and "### not a heading" not in text      # fenced code is left alone
    assert kb.format_context("technical/x", []).endswith("(no current facts)")


def test_search_needs_a_word():
    with pytest.raises(kb.KbError):
        kb.read_search(RecordingTx(), ROOT, "a of ? the")


def test_fact_rejects_both_timelines():
    with pytest.raises(kb.KbError, match="not both"):
        kb.read_fact(RecordingTx(), ROOT, "x", as_of="2026-01-01", kb_as_of="2026-01-01")


# ---------------------------------------------------------------- integration: a fact with history

POOL, COMM, RETIRED = "it-pool-restart", "it-commingling", "it-retired"


def build_history(tx):
    """it-pool-restart: v1 created Jan; v2 changed the rule on 1 Mar; v3 (recorded 1 Apr) corrects v2 and carries
    its business dates. it-commingling: one current version plus an open draft. Links: pool depends_on commingling,
    pool describes component it-engine in repo it/engine."""
    new_fact(tx, POOL, "business/pools")
    add_version(tx, POOL, "p-v1", {
        "title": "Pool restart replays histories newest first", "summary": "Old rule.", "status": "superseded",
        "statement": "Replay sport event histories newest first.", "keywords": ["restart"],
        "valid_from": utc(2026, 1, 10), "valid_to": utc(2026, 3, 1),
        "recorded_at": utc(2026, 1, 10), "recorded_to": utc(2026, 3, 1)})
    add_version(tx, POOL, "p-v2", {
        "title": "Pool restart replays histories by id", "summary": "Changed rule, later found wrong.",
        "status": "superseded", "change_type": "change", "statement": "Replay by SEH.id.",
        "valid_from": utc(2026, 3, 1), "recorded_at": utc(2026, 3, 1), "recorded_to": utc(2026, 4, 1)})
    add_version(tx, POOL, "p-v3", {
        "title": "Pool restart replays sport event histories oldest first", "summary": "Corrected rule.",
        "change_type": "correction", "statement": "Replay SEH by created_at ascending during pool restart.",
        "keywords": ["restart", "RU"], "why": "v2 misread the code", "valid_from": utc(2026, 3, 1),
        "recorded_at": utc(2026, 4, 1)}, current=True)
    supersede(tx, "p-v2", "p-v1")
    supersede(tx, "p-v3", "p-v2")

    new_fact(tx, COMM, "technical/architecture/commingling")
    add_version(tx, COMM, "c-v1", {"title": "Commingling host and guest", "summary": "Host actions fan out.",
                                   "statement": "Guests replicate pools after a restart of the host."}, current=True)
    add_version(tx, COMM, "c-d1", {"title": "Draft: zebra rule", "summary": "Draft only.", "status": "draft",
                                   "statement": "zebra"})

    tx.run("MATCH (a:KbFact {id: $a}), (b:KbFact {id: $b}) CREATE (a)-[:KB_RELATES_TO {rel: 'depends_on'}]->(b) "
           "CREATE (a)-[:KB_DESCRIBES]->(s:KbSystemComponent {name: 'it-engine', kind: 'service', description: 'Tote engine'}) "
           "CREATE (s)-[:KB_IMPLEMENTED_IN]->(:KbCodeRepo {path: 'it/engine', web_url: 'https://example.invalid/it/engine'})",
           a=POOL, b=COMM).consume()

    # it-retired: in force from 1 Jan, retracted on 1 Feb (no current version afterwards).
    new_fact(tx, RETIRED, "business/pools")
    add_version(tx, RETIRED, "r-v1", {
        "title": "Retired rule", "summary": "No longer true.", "status": "retracted",
        "valid_from": utc(2026, 1, 1), "valid_to": utc(2026, 2, 1),
        "recorded_at": utc(2026, 1, 1), "recorded_to": utc(2026, 2, 1)})


@it
def test_history_scenario_is_valid_kb_data(tx):
    build_history(tx)
    assert kb.check_problems(tx, kb.integrity_checks(ROOT)) == []


@it
def test_fact_returns_the_current_version(tx):
    build_history(tx)
    row = kb.read_fact(tx, ROOT, POOL)
    assert row["version"]["version_id"] == "p-v3" and row["category"] == "business/pools"
    assert row["author"] == "it@colossusbets.com" and row["version"]["why"] == "v2 misread the code"
    assert "search_text" not in row["version"]
    assert kb.read_fact(tx, ROOT, "it-missing") is None


@it
@pytest.mark.parametrize("at,expected", [
    ("2025-12-01", None),         # before the fact existed
    ("2026-02-01", "p-v1"),       # the original rule
    ("2026-03-15", "p-v3"),       # the corrected rule: v2 was wrong, v3 carries its business dates
    ("2026-06-01T00:00:00Z", "p-v3"),
])
def test_fact_as_of_business_time(tx, at, expected):
    build_history(tx)
    row = kb.read_fact(tx, ROOT, POOL, as_of=at)
    assert (row["version"]["version_id"] if row else None) == expected


@it
@pytest.mark.parametrize("at,expected", [
    ("2025-12-01", None),
    ("2026-02-01", "p-v1"),
    ("2026-03-15", "p-v2"),       # what the KB said then, before the correction was recorded
    ("2026-05-01", "p-v3"),
])
def test_fact_kb_as_of_record_time(tx, at, expected):
    build_history(tx)
    row = kb.read_fact(tx, ROOT, POOL, kb_as_of=at)
    assert (row["version"]["version_id"] if row else None) == expected


@it
@pytest.mark.parametrize("option,at,expected", [
    ("as_of", "2026-01-15", "r-v1"), ("as_of", "2026-02-15", None),
    ("kb_as_of", "2026-01-15", "r-v1"), ("kb_as_of", "2026-02-15", None),
])
def test_retracted_fact_by_date(tx, option, at, expected):
    build_history(tx)
    row = kb.read_fact(tx, ROOT, RETIRED, **{option: at})
    assert (row["version"]["version_id"] if row else None) == expected


@it
def test_retracted_fact_has_no_current_version_and_says_why(tx):
    build_history(tx)
    assert kb.read_fact(tx, ROOT, RETIRED) is None
    assert "no current version of 'it-retired' (retracted?)" in kb.missing_fact_message(tx, ROOT, RETIRED)
    assert "no version of 'it-retired' at 2026-02-15" in kb.missing_fact_message(tx, ROOT, RETIRED, "2026-02-15")
    assert kb.missing_fact_message(tx, ROOT, "it-missing") == "no fact 'it-missing'"
    assert [r["status"] for r in kb.read_history(tx, ROOT, RETIRED)] == ["retracted"]
    assert RETIRED not in [r["id"] for r in kb.read_current_by_category(tx, ROOT, "business")]


@it
def test_a_stem_does_not_double_a_words_weight(tx):
    new_fact(tx, "it-status")
    add_version(tx, "it-status", "s-v1", {"title": "Leg status rules"}, current=True)
    new_fact(tx, "it-poolrules")
    add_version(tx, "it-poolrules", "q-v1", {"title": "Pool rules"}, current=True)
    scores = {h["id"]: h["score"] for h in it_search(tx, "pool status")}
    assert scores == {"it-status": 4, "it-poolrules": 4}       # 'status' and its stem 'statu' count once


@it
def test_history_lists_versions_oldest_first_with_links(tx):
    build_history(tx)
    rows = kb.read_history(tx, ROOT, POOL)
    assert [(r["version_id"], r["supersedes"], r["current"]) for r in rows] == [
        ("p-v1", None, False), ("p-v2", "p-v1", False), ("p-v3", "p-v2", True)]
    assert [r["change_type"] for r in rows] == ["create", "change", "correction"]
    assert kb.read_history(tx, ROOT, "it-missing") == []


@it
def test_search_ranks_current_versions_only(tx):
    build_history(tx)
    hits = it_search(tx, "pool restart")
    ids = [h["id"] for h in hits]
    assert ids.index(POOL) < ids.index(COMM)               # title + keywords beat a statement-only match
    assert it_search(tx, "newest") == []          # only in the superseded v1
    assert it_search(tx, "zebra") == []           # only in a draft
    assert [h["id"] for h in it_search(tx, "restarts")][:1] == [POOL]   # stem 'restart'


@it
def test_current_by_category_matches_whole_path_segments(tx):
    build_history(tx)
    ids = lambda prefix: [r["id"] for r in kb.read_current_by_category(tx, ROOT, prefix) if r["id"].startswith("it-")]
    assert ids("business") == [POOL]
    assert ids("business/pools") == [POOL]
    assert ids("business/pool") == []
    assert sorted(ids("")) == sorted([POOL, COMM])        # the retracted fact isn't current
    assert ids("technical") == [COMM]                       # one row per fact, the draft isn't listed


@it
def test_context_returns_current_statements_by_whole_path_segments(tx):
    build_history(tx)
    rows = lambda prefix: [r for r in kb.read_context(tx, ROOT, prefix) if r["id"].startswith("it-")]
    assert [(r["id"], r["statement"]) for r in rows("business/pools")] == [
        (POOL, "Replay SEH by created_at ascending during pool restart.")]   # the current version, not v1 or v2
    assert rows("business/pool") == []
    assert [r["statement"] for r in rows("technical")] == ["Guests replicate pools after a restart of the host."]


@it
def test_related_one_hop_both_directions(tx):
    build_history(tx)
    out = kb.read_related(tx, ROOT, POOL)
    assert out["facts"] == [{"direction": "out", "rel": "depends_on", "id": COMM, "title": "Commingling host and guest",
                             "summary": "Host actions fan out."}]
    assert out["components"] == [{"name": "it-engine", "kind": "service", "description": "Tote engine",
                                  "repos": ["it/engine"]}]
    back = kb.read_related(tx, ROOT, COMM)
    assert [(f["direction"], f["id"]) for f in back["facts"]] == [("in", POOL)]
    assert kb.read_related(tx, ROOT, "it-missing") is None


@it
def test_text_and_json_output(tx):
    build_history(tx)
    row = kb.read_fact(tx, ROOT, POOL)
    text = kb.format_fact(row)
    assert "Pool restart replays sport event histories oldest first" in text and "why: v2 misread the code" in text
    assert "valid 2026-03-01 -> -" in text
    assert "version p-v3 |" in text                          # what --expected-current needs
    assert json.loads(json.dumps(row, default=kb._json_default))["version"]["valid_from"].startswith("2026-03-01")
    assert "p-v2" in kb.format_history(kb.read_history(tx, ROOT, POOL))
    assert "depends_on" in kb.format_related(kb.read_related(tx, ROOT, POOL))


@it
def test_categories_mark_leaves_and_count_current_facts(tx):
    build_history(tx)
    rows = {r["path"]: r for r in kb.read_categories(tx, ROOT)}
    assert rows["business"]["leaf"] is False and rows["business/pools"]["leaf"] is True
    assert rows["business/glossary"]["leaf"] is True
    pools = rows["business/pools"]["facts"]
    assert pools == len(kb.read_current_by_category(tx, ROOT, "business/pools", 200)) and pools >= 1   # POOL is current
    lines = kb.format_categories(list(rows.values())).split("\n")
    assert "business: Business" in lines and f"  business/pools  [leaf, {pools} fact{'' if pools == 1 else 's'}]: Pool Business Rules" in lines


@it
def test_cli_reads_on_staging(capsys):
    assert kb.main(["read", "search", "--q", "pool"]) == 0
    assert kb.main(["read", "fact", "--id", "it-missing"]) == 1
    assert "no fact 'it-missing'" in capsys.readouterr().out
    assert kb.main(["read", "fact", "--id", "x", "--as-of", "2026-13-01"]) == 2
