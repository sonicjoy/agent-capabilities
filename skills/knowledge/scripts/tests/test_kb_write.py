"""Tests for `kb.py write`. Integration tests run on KB staging inside rolled-back transactions (KB_IT=1)."""
import re
from datetime import datetime, timezone

import pytest

import kb
import kbwrite
from conftest import ROOT, integration_enabled, it_search

it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")
WRITE_TEMPLATES = sorted(p.stem for p in (ROOT / "graph/queries/write").glob("*.cypher"))
ME, OTHER = "it-author@colossusbets.com", "it-approver@colossusbets.com"
LEAF = "technical/conventions/code-quality"


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def fact(fid="it-w", **kw):
    base = dict(id=fid, why="test", source_type="test", source_refs=["kb/6"], author=ME, via="agent",
                category=LEAF, kind="rule", title="Restart order", summary="Replay oldest first.",
                statement="Replay SEH oldest first.", keywords=["restart"])
    base.update(kw)
    return kbwrite.FactInput(**base)


# ---------------------------------------------------------------- unit: no database

@pytest.mark.parametrize("name", WRITE_TEMPLATES)
def test_write_templates_touch_only_kb_elements_and_never_delete_nodes(name):
    code = re.sub(r"//[^\n]*", "", kb.load_template(ROOT, "write", name))
    assert "DETACH" not in code, name
    assert all(label.startswith("Kb") for label in re.findall(r"\(\w*:(\w+)", code)), name
    assert all(rel.startswith("KB_") for rel in re.findall(r"\[\w*:(\w+)", code)), name
    if re.search(r"\bDELETE\b", code):   # only relationship deletes: a category move, or removing a mistaken link
        assert name in ("move_category", "unlink_relates_to", "unlink_describes", "unlink_implemented_in"), name
        assert re.search(r"\[r:KB_(IN_CATEGORY|RELATES_TO|DESCRIBES|IMPLEMENTED_IN)\b", code), name


@pytest.mark.parametrize("kwargs,match", [
    ({"id": "Bad Id"}, "kebab"),
    ({"why": " "}, "--why"),
    ({"source_refs": []}, "source-ref"),
    ({"via": "robot"}, "--via"),
    ({"kind": "opinion"}, "--kind"),
    ({"keywords": ["ok", " "]}, "keywords"),
    ({"keywords": ["pools: SEP"]}, "keywords can't contain"),
    ({"keywords": ["SEP/MVP"]}, "keywords can't contain"),
    ({"keywords": ["**bold**"]}, "keywords can't contain"),
    ({"title": "  "}, "--title"),
    ({"change_type": "rewrite"}, "--change-type"),
    ({"author": "not-an-email"}, "--author"),
])
def test_input_validation(kwargs, match):
    with pytest.raises(kb.KbError, match=match):
        kbwrite.write_fact(_NoDb(), ROOT, fact(**kwargs), now=utc(2026, 6, 1))


class _NoDb:
    def run(self, *a, **k):
        return []


def test_future_valid_from_is_refused():
    with pytest.raises(kb.KbError, match="future"):
        kbwrite.write_fact(_NoDb(), ROOT, fact(valid_from=utc(2026, 7, 1)), now=utc(2026, 6, 1))


@pytest.mark.parametrize("path,risky", [("business/pools", True), ("business/pools/withdrawals", True),
                                        ("business/poolside", False), ("technical/cbtote", False)])
def test_high_risk_categories(path, risky):
    assert kbwrite.is_high_risk(path) is risky


def test_native_datetimes_use_offset_utc():
    """Neo4j returns a named 'UTC' zone; written back, it wouldn't equal the same instant stored with +00:00."""
    from zoneinfo import ZoneInfo

    class FakeNeoDateTime:
        def to_native(self):
            return datetime(2026, 1, 10, tzinfo=ZoneInfo("UTC"))

    out = kbwrite._native({"a": [FakeNeoDateTime()]})["a"][0]
    assert out == utc(2026, 1, 10) and out.tzinfo is timezone.utc


@pytest.mark.parametrize("text,hit", [
    ("password: from the secret store", False), ("Set COLOSSUS_KB_PASSWORD at user level", False),
    ("token = $TOKEN", False), ("api_key: <from-secrets-manager>", False), ("use the token from the vault", False),
    ("password=hunter2222", True), ("neo4j+s://neo4j:s3cr3tpw@host", True), ("AKIAABCDEFGHIJKLMNOP", True),
    ("glpat-abcdefghijklmnopqrstuv", True), ("-----BEGIN RSA PRIVATE KEY-----", True),
])
def test_secret_scan(text, hit):
    assert bool(kbwrite.find_secrets({"statement": text})) is hit


def test_write_refuses_secrets_without_echoing_them():
    with pytest.raises(kb.KbError) as err:
        kbwrite.write_fact(_LockedNone(), ROOT, fact(why="token: abcdef123456"), now=utc(2026, 6, 1))
    assert "--why looks like it contains" in str(err.value) and "abcdef123456" not in str(err.value)


class _LockedNone(_NoDb):
    """No fact yet, and every category exists as an empty leaf."""
    def run(self, query, **params):
        return [{"path": params.get("path"), "has_children": False, "facts": 0}] if "has_children" in query else []


class _DraftByMe(_NoDb):
    """A draft written by ME, and a KB that knows OTHER (enough for the checks before promote locks the fact)."""
    def run(self, query, **params):
        if "email" in params:
            return [_Record({"email": params["email"]})] if params["email"] == OTHER else []
        return [_Record({"id": "x", "status": "draft", "author": ME})]


class _Record(dict):
    def data(self):
        return dict(self)


NOTE = "https://gitlab.colossusbets.com/colossus/x/-/work_items/1#note_1"


@pytest.mark.parametrize("runner,kwargs,match", [
    (ME, {}, "you wrote this draft"),
    (ME, {"confirmed_by": OTHER}, "you wrote this draft"),
    (ME, {"evidence": NOTE}, "you wrote this draft"),
    (ME, {"confirmed_by": "", "evidence": NOTE}, "--confirmed-by must be an email"),
    (ME, {"confirmed_by": "will", "evidence": NOTE}, "--confirmed-by must be an email"),
    (ME, {"confirmed_by": ME.upper(), "evidence": NOTE}, "different person"),
    (ME, {"confirmed_by": OTHER, "evidence": "  "}, "--evidence must be an http"),
    (ME, {"confirmed_by": OTHER, "evidence": "Will said ok"}, "--evidence must be an http"),
    (ME, {"confirmed_by": OTHER, "evidence": "https://gitlab/x"}, "--evidence must be an http"),
    (ME, {"confirmed_by": OTHER, "evidence": "https://user:hunter2222@gitlab.colossusbets.com/x"}, "--evidence looks like"),
    (ME, {"confirmed_by": "will@colosusbets.com", "evidence": NOTE}, "isn't in the KB yet"),
    (ME, {"confirmed_by": OTHER, "evidence": NOTE, "approver_name": "Will"}, "--approver-name doesn't go"),
    (OTHER, {"confirmed_by": "third@colossusbets.com", "evidence": NOTE}, "only for the draft's author"),
    (OTHER, {"evidence": NOTE}, "only for the draft's author"),
    (OTHER, {"confirmed_by_name": "Third"}, "only for the draft's author"),
])
def test_author_promote_needs_a_named_confirmer_and_evidence(runner, kwargs, match):
    with pytest.raises(kb.KbError, match=match):
        kbwrite.promote(_DraftByMe(), ROOT, "v", runner, None, now=utc(2026, 6, 1), **kwargs)


def test_evidence_accepts_gitlab_and_slack_links():
    assert kbwrite.EVIDENCE_URL.match(NOTE)
    assert kbwrite.EVIDENCE_URL.match("https://colossusbets.slack.com/archives/C01/p1760000000000")


def test_identity_comes_from_the_machine(monkeypatch, capsys):
    monkeypatch.setenv("COLOSSUS_KB_AUTHOR", "Me@Colossusbets.com")
    assert kb.kb_identity() == "me@colossusbets.com"
    assert kb._actor(None, "author") == "me@colossusbets.com"
    with pytest.raises(kb.KbError, match="isn't you"):
        kb._actor("someone.else@colossusbets.com", "approver")
    assert kb.main(["write", "retract", "--id", "x", "--why", "w", "--expected-current", "v",
                    "--author", "someone.else@colossusbets.com"]) == 2
    assert "isn't you" in capsys.readouterr().err


def test_cli_refuses_when_frozen(monkeypatch, capsys):
    monkeypatch.setenv("COLOSSUS_KB_FREEZE", "1")
    assert kb.main(["write", "component", "--name", "x"]) == 2
    assert "frozen" in capsys.readouterr().err


# ---------------------------------------------------------------- integration helpers

def current(tx, fid):
    row = kb.read_fact(tx, ROOT, fid)
    return row["version"] if row else None


def as_of(tx, fid, at):
    row = kb.read_fact(tx, ROOT, fid, as_of=at)
    return row["version"]["version_id"] if row else None


def kb_as_of(tx, fid, at):
    row = kb.read_fact(tx, ROOT, fid, kb_as_of=at)
    return row["version"]["version_id"] if row else None


def create_v1(tx, fid="it-w", valid_from=utc(2026, 1, 10), now=utc(2026, 1, 10)):
    return kbwrite.write_fact(tx, ROOT, fact(fid, valid_from=valid_from), now=now)


# ---------------------------------------------------------------- integration: facts

@it
def test_create_writes_an_active_current_version(tx):
    r = create_v1(tx)
    assert (r["status"], r["change_type"]) == ("active", "create")
    v = current(tx, "it-w")
    assert v["version_id"] == r["version_id"] and v["source_refs"] == ["kb/6"]
    assert kb.read_fact(tx, ROOT, "it-w")["author"] == ME
    assert [h["id"] for h in it_search(tx, "restart")] == ["it-w"]   # search_text written


@it
def test_create_refuses_non_leaf_and_unknown_categories_and_expected_current(tx):
    with pytest.raises(kb.KbError, match="sub-categories"):
        kbwrite.write_fact(tx, ROOT, fact(category="technical"), now=utc(2026, 1, 1))
    with pytest.raises(kb.KbError, match="no category"):
        kbwrite.write_fact(tx, ROOT, fact(category="technical/nope"), now=utc(2026, 1, 1))
    with pytest.raises(kb.KbError, match="doesn't exist yet"):
        kbwrite.write_fact(tx, ROOT, fact(expected_current="x"), now=utc(2026, 1, 1))


@it
def test_change_closes_the_old_version_on_both_timelines(tx):
    v1 = create_v1(tx)["version_id"]
    r = kbwrite.write_fact(tx, ROOT, fact(statement="Replay by id.", why="rule changed in release 42",
                                          valid_from=utc(2026, 3, 1), expected_current=v1), now=utc(2026, 3, 2))
    v2 = r["version_id"]
    assert r["superseded"] == v1 and r["change_type"] == "change"
    assert (as_of(tx, "it-w", "2026-02-01"), as_of(tx, "it-w", "2026-04-01")) == (v1, v2)
    assert (kb_as_of(tx, "it-w", "2026-03-01T12:00:00Z"), kb_as_of(tx, "it-w", "2026-03-03")) == (v1, v2)
    hist = kb.read_history(tx, ROOT, "it-w")
    assert [(h["version_id"], h["status"], h["supersedes"]) for h in hist] == [(v1, "superseded", None), (v2, "active", v1)]


@it
def test_change_needs_the_right_expected_current_and_real_content(tx):
    v1 = create_v1(tx)["version_id"]
    with pytest.raises(kb.KbError, match="changed: its latest version is"):
        kbwrite.write_fact(tx, ROOT, fact(statement="x", expected_current="stale"), now=utc(2026, 3, 1))
    with pytest.raises(kb.KbError, match="changed: its latest version is"):
        kbwrite.write_fact(tx, ROOT, fact(statement="x"), now=utc(2026, 3, 1))     # missing --expected-current
    with pytest.raises(kb.KbError, match="nothing changed"):
        kbwrite.write_fact(tx, ROOT, fact(expected_current=v1), now=utc(2026, 3, 1))
    with pytest.raises(kb.KbError, match="after the current version's start"):
        kbwrite.write_fact(tx, ROOT, fact(statement="x", expected_current=v1, valid_from=utc(2026, 1, 1)),
                           now=utc(2026, 3, 1))


@it
def test_correction_inherits_dates_and_hides_the_wrong_version_from_business_time(tx):
    v1 = create_v1(tx)["version_id"]
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="Replay by id.", valid_from=utc(2026, 3, 1), expected_current=v1),
                            now=utc(2026, 3, 1))["version_id"]
    r = kbwrite.write_fact(tx, ROOT, fact(statement="Replay by created_at ascending.", change_type="correction",
                                          why="v2 misread the code", expected_current=v2), now=utc(2026, 4, 1))
    v3 = r["version_id"]
    assert r["predecessor_valid_to_moved"] is None
    assert current(tx, "it-w")["valid_from"].iso_format().startswith("2026-03-01")
    assert as_of(tx, "it-w", "2026-03-15") == v3          # the corrected v2 is skipped for business time
    assert kb_as_of(tx, "it-w", "2026-03-15") == v2       # but it is what the KB said then
    assert as_of(tx, "it-w", "2026-02-01") == v1


@it
def test_correction_can_move_the_start_and_moves_the_predecessor_end(tx):
    v1 = create_v1(tx)["version_id"]
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="New rule.", valid_from=utc(2026, 3, 1), expected_current=v1),
                            now=utc(2026, 3, 1))["version_id"]
    r = kbwrite.write_fact(tx, ROOT, fact(statement="New rule, really from 15 Feb.", change_type="correction",
                                          valid_from=utc(2026, 2, 15), expected_current=v2), now=utc(2026, 4, 1))
    v3 = r["version_id"]
    assert r["predecessor_valid_to_moved"] == v1
    assert as_of(tx, "it-w", "2026-02-10") == v1
    assert as_of(tx, "it-w", "2026-02-20") == v3          # was v1 before the correction
    assert as_of(tx, "it-w", "2026-03-15") == v3
    hist = {h["version_id"]: h for h in kb.read_history(tx, ROOT, "it-w")}
    assert hist[v1]["valid_to"].iso_format().startswith("2026-02-15")


@it
def test_correction_cannot_start_before_the_previous_rule(tx):
    v1 = create_v1(tx)["version_id"]
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="New rule.", valid_from=utc(2026, 3, 1), expected_current=v1),
                            now=utc(2026, 3, 1))["version_id"]
    with pytest.raises(kb.KbError, match="after the previous rule's start"):
        kbwrite.write_fact(tx, ROOT, fact(statement="x", change_type="correction", valid_from=utc(2026, 1, 1),
                                          expected_current=v2), now=utc(2026, 4, 1))


@it
def test_change_can_move_category_and_records_it(tx):
    v1 = create_v1(tx)["version_id"]
    r = kbwrite.write_fact(tx, ROOT, fact(category="technical/conventions/data-fixes", why="belongs with data fixes",
                                          expected_current=v1), now=utc(2026, 3, 1))
    assert r["moved_from"] == LEAF
    assert kb.read_fact(tx, ROOT, "it-w")["category"] == "technical/conventions/data-fixes"
    assert len(kb.read_history(tx, ROOT, "it-w")) == 2


# ---------------------------------------------------------------- integration: retract

@it
def test_retract_ends_the_rule_and_a_change_can_bring_it_back(tx):
    v1 = create_v1(tx)["version_id"]
    kbwrite.retract(tx, ROOT, "it-w", "feature removed", ["MR !99"], ME, v1, now=utc(2026, 3, 1))
    assert current(tx, "it-w") is None
    assert (as_of(tx, "it-w", "2026-02-01"), as_of(tx, "it-w", "2026-04-01")) == (v1, None)
    with pytest.raises(kb.KbError, match="on or after the retraction"):
        kbwrite.write_fact(tx, ROOT, fact(statement="Back.", valid_from=utc(2026, 2, 1), expected_current=v1),
                           now=utc(2026, 5, 1))
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="Back again.", valid_from=utc(2026, 5, 1), expected_current=v1),
                            now=utc(2026, 5, 1))["version_id"]
    assert current(tx, "it-w")["version_id"] == v2 and as_of(tx, "it-w", "2026-04-01") is None


@it
def test_retract_never_valid_removes_it_from_business_time_only(tx):
    v1 = create_v1(tx)["version_id"]
    kbwrite.retract(tx, ROOT, "it-w", "bad ingest, never true", ["ingest:x"], ME, v1, never_valid=True,
                    now=utc(2026, 3, 1))
    assert [as_of(tx, "it-w", d) for d in ("2026-01-09", "2026-01-10", "2026-02-01", "2026-06-01")] == [None] * 4
    assert kb_as_of(tx, "it-w", "2026-02-01") == v1         # the KB did say it then
    assert kb.read_history(tx, ROOT, "it-w")[0]["status"] == "retracted"


@it
def test_retract_needs_current_and_expected(tx):
    v1 = create_v1(tx)["version_id"]
    with pytest.raises(kb.KbError, match="changed"):
        kbwrite.retract(tx, ROOT, "it-w", "x", ["y"], ME, "stale", now=utc(2026, 3, 1))
    kbwrite.retract(tx, ROOT, "it-w", "x", ["y"], ME, v1, now=utc(2026, 3, 1))
    with pytest.raises(kb.KbError, match="no current version"):
        kbwrite.retract(tx, ROOT, "it-w", "x", ["y"], ME, v1, now=utc(2026, 3, 2))


# ---------------------------------------------------------------- integration: drafts and approval

@it
def test_pools_writes_are_drafts_and_need_another_person_to_promote(tx):
    r = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools"), now=utc(2026, 1, 10))
    assert r["status"] == "draft" and "needs approval" in r["note"]
    assert current(tx, "it-pool") is None and it_search(tx, "restart") == []
    with pytest.raises(kb.KbError, match="you wrote this draft"):
        kbwrite.promote(tx, ROOT, r["version_id"], ME.upper(), None, now=utc(2026, 1, 11))
    p = kbwrite.promote(tx, ROOT, r["version_id"], OTHER, None, now=utc(2026, 1, 11))
    assert p["approved_by"] == OTHER and current(tx, "it-pool")["version_id"] == r["version_id"]
    assert kb.read_fact(tx, ROOT, "it-pool")["approved_by"] == [OTHER]
    assert kb.read_fact(tx, ROOT, "it-pool")["version"]["approval_recorded_by"] is None


@it
def test_author_promotes_own_draft_on_a_named_confirmation(tx):
    r = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools"), now=utc(2026, 1, 10))
    confirmer = "it-confirmer@colossusbets.com"                 # not in the KB yet: needs a name to be added
    with pytest.raises(kb.KbError, match="isn't in the KB yet"):
        kbwrite.promote(tx, ROOT, r["version_id"], ME, None, now=utc(2026, 1, 11), confirmed_by=confirmer, evidence=NOTE)
    p = kbwrite.promote(tx, ROOT, r["version_id"], ME, None, now=utc(2026, 1, 11), confirmed_by=confirmer,
                        evidence=NOTE, confirmed_by_name="IT Confirmer")
    assert p["approved_by"] == confirmer and p["approval_recorded_by"] == ME and p["approval_evidence"] == NOTE
    row = kb.read_fact(tx, ROOT, "it-pool")
    assert row["approved_by"] == [confirmer] and row["version"]["approval_recorded_by"] == ME
    shown = f"approved by {confirmer} (recorded by {ME}, evidence: {NOTE})"
    assert shown in kb.format_fact(row) and shown in kb.format_history(kb.read_history(tx, ROOT, "it-pool"))
    assert tx.run("MATCH (p:KbPerson {email: $e}) RETURN p.name AS n", e=confirmer).single()["n"] == "IT Confirmer"


@it
def test_draft_change_promotes_as_a_change(tx):
    v1 = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools", valid_from=utc(2026, 1, 10)),
                            now=utc(2026, 1, 10))["version_id"]
    kbwrite.promote(tx, ROOT, v1, OTHER, None, now=utc(2026, 1, 11))
    d = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools", statement="Changed.",
                                          valid_from=utc(2026, 3, 1), expected_current=v1), now=utc(2026, 3, 1))
    assert d["status"] == "draft" and current(tx, "it-pool")["version_id"] == v1     # the draft isn't live yet
    with pytest.raises(kb.KbError, match="changed since the draft"):
        kbwrite.promote(tx, ROOT, d["version_id"], OTHER, None, now=utc(2026, 3, 2))
    p = kbwrite.promote(tx, ROOT, d["version_id"], OTHER, v1, now=utc(2026, 3, 2))
    assert p["superseded"] == v1 and as_of(tx, "it-pool", "2026-02-01") == v1
    assert as_of(tx, "it-pool", "2026-03-15") == d["version_id"]


# ---------------------------------------------------------------- integration: links, components, repos, categories

@it
def test_links_components_and_repos(tx):
    create_v1(tx, "it-a")
    create_v1(tx, "it-b")
    kbwrite.link(tx, ROOT, "relates_to", "it-a", "it-b", "depends_on")
    with pytest.raises(kb.KbError, match="--rel"):
        kbwrite.link(tx, ROOT, "relates_to", "it-a", "it-b", "likes")
    with pytest.raises(kb.KbError, match="nothing linked"):
        kbwrite.link(tx, ROOT, "relates_to", "it-a", "it-missing", "see_also")
    kbwrite.upsert_component(tx, ROOT, "it-engine", "service", "Tote engine")
    kbwrite.upsert_repo(tx, ROOT, "it/engine", "https://example.invalid/it/engine")
    kbwrite.link(tx, ROOT, "describes", "it-a", "it-engine")
    kbwrite.link(tx, ROOT, "implemented_in", "it-engine", "it/engine")
    kbwrite.link(tx, ROOT, "implemented_in", "it-a", "it/engine")
    out = kb.read_related(tx, ROOT, "it-a")
    assert [(f["rel"], f["id"]) for f in out["facts"]] == [("depends_on", "it-b")]
    assert out["components"][0]["repos"] == ["it/engine"] and out["repos"][0]["path"] == "it/engine"


@it
def test_categories_respect_the_leaf_rule(tx):
    kbwrite.create_category(tx, ROOT, "business/glossary/terms", "Terms", None)   # glossary has no facts yet
    with pytest.raises(kb.KbError, match="holds facts"):
        create_v1(tx)                                                            # puts a fact in code-quality
        kbwrite.create_category(tx, ROOT, f"{LEAF}/sub", "Sub", None)
    with pytest.raises(kb.KbError, match="already exists"):
        kbwrite.create_category(tx, ROOT, "business/glossary/terms", "Terms", None)


# ---------------------------------------------------------------- integration: guard and CLI

@it
def test_a_write_is_refused_if_the_kb_would_fail_integrity(tx):
    create_v1(tx, "it-a")
    tx.run("MATCH (:KbFact {id: 'it-a'})-[r:KB_IN_CATEGORY]->() DELETE r").consume()   # break something
    with pytest.raises(kb.KbError, match="fact_category_count"):
        kbwrite.upsert_component(tx, ROOT, "it-x", None, None)


@it
def test_cli_dry_run_writes_nothing(capsys):
    args = ["write", "fact", "--id", "it-cli-dry-run", "--category", LEAF, "--kind", "rule", "--title", "T",
            "--summary", "S", "--statement", "B", "--why", "w", "--source-type", "test", "--source-ref", "kb/6",
            "--via", "agent", "--dry-run"]
    assert kb.main(args) == 0
    assert "DRY RUN (rolled back)" in capsys.readouterr().out
    assert kb.main(["read", "fact", "--id", "it-cli-dry-run"]) == 1


# ---------------------------------------------------------------- review of !5

@it
def test_promote_refuses_a_draft_written_against_an_older_version(tx):
    v1 = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools", valid_from=utc(2026, 1, 10)),
                            now=utc(2026, 1, 10))["version_id"]
    kbwrite.promote(tx, ROOT, v1, OTHER, None, now=utc(2026, 1, 11))
    old_draft = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools", statement="Draft A.",
                                                  valid_from=utc(2026, 2, 1), expected_current=v1), now=utc(2026, 2, 1))
    newer = kbwrite.write_fact(tx, ROOT, fact("it-pool", category="business/pools", statement="Draft B.",
                                              valid_from=utc(2026, 3, 1), expected_current=v1), now=utc(2026, 3, 1))
    v2 = kbwrite.promote(tx, ROOT, newer["version_id"], OTHER, v1, now=utc(2026, 3, 2))["version_id"]
    with pytest.raises(kb.KbError, match="was written against"):
        kbwrite.promote(tx, ROOT, old_draft["version_id"], OTHER, v2, now=utc(2026, 3, 3))   # would overwrite v2
    assert current(tx, "it-pool")["version_id"] == v2


@it
def test_never_valid_is_refused_when_it_would_leave_a_gap(tx):
    v1 = create_v1(tx)["version_id"]
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="Changed.", valid_from=utc(2026, 3, 1), expected_current=v1),
                            now=utc(2026, 3, 1))["version_id"]
    with pytest.raises(kb.KbError, match="would leave a gap"):
        kbwrite.retract(tx, ROOT, "it-w", "never true", ["x"], ME, v2, never_valid=True, now=utc(2026, 4, 1))
    v3 = kbwrite.write_fact(tx, ROOT, fact(statement="Replay SEH oldest first.", change_type="correction",
                                          why="the change was wrong", expected_current=v2), now=utc(2026, 4, 1))["version_id"]
    assert as_of(tx, "it-w", "2026-02-01") == v1 and as_of(tx, "it-w", "2026-05-01") == v3


@it
def test_retraction_audit_is_readable(tx):
    v1 = create_v1(tx)["version_id"]
    kbwrite.retract(tx, ROOT, "it-w", "feature removed", ["MR !99"], ME, v1, now=utc(2026, 3, 1))
    h = kb.read_history(tx, ROOT, "it-w")[0]
    assert (h["retract_why"], h["retract_source_refs"], h["retracted_by"]) == ("feature removed", ["MR !99"], ME)
    v = kb.read_fact(tx, ROOT, "it-w", kb_as_of="2026-02-01")["version"]
    assert v["retract_why"] == "feature removed"


@it
def test_reactivation_copies_the_retracted_content(tx):
    v1 = create_v1(tx)["version_id"]
    kbwrite.retract(tx, ROOT, "it-w", "paused", ["x"], ME, v1, now=utc(2026, 3, 1))
    inp = kbwrite.FactInput(id="it-w", why="back", source_type="test", source_refs=["x"], author=ME, via="agent",
                            statement="Back, unchanged otherwise.", valid_from=utc(2026, 4, 1), expected_current=v1)
    kbwrite.write_fact(tx, ROOT, inp, now=utc(2026, 4, 1))
    v = current(tx, "it-w")
    assert (v["title"], v["kind"], v["statement"]) == ("Restart order", "rule", "Back, unchanged otherwise.")


@it
def test_overlapping_business_time_is_refused(tx):
    v1 = create_v1(tx)["version_id"]
    kbwrite.retract(tx, ROOT, "it-w", "paused", ["x"], ME, v1, now=utc(2026, 3, 1))
    v2 = kbwrite.write_fact(tx, ROOT, fact(statement="Back.", valid_from=utc(2026, 5, 1), expected_current=v1),
                            now=utc(2026, 5, 1))["version_id"]
    with pytest.raises(kb.KbError, match="business_overlap"):   # a correction may not move into the old rule's period
        kbwrite.write_fact(tx, ROOT, fact(statement="Back, earlier.", change_type="correction",
                                          valid_from=utc(2026, 2, 1), expected_current=v2), now=utc(2026, 6, 1))


@it
def test_unlink_and_ambiguous_link_sources(tx):
    create_v1(tx, "it-a")
    create_v1(tx, "it-b")
    kbwrite.link(tx, ROOT, "relates_to", "it-a", "it-b", "see_also")
    assert kbwrite.unlink(tx, ROOT, "relates_to", "it-a", "it-b", "see_also")["removed"] == 1
    assert kb.read_related(tx, ROOT, "it-a")["facts"] == []
    with pytest.raises(kb.KbError, match="no relates_to link"):
        kbwrite.unlink(tx, ROOT, "relates_to", "it-a", "it-b", "see_also")
    kbwrite.upsert_component(tx, ROOT, "it-a", "service", None)        # same name as a fact
    kbwrite.upsert_repo(tx, ROOT, "it/engine", None)
    with pytest.raises(kb.KbError, match="both a fact id and a component name"):
        kbwrite.link(tx, ROOT, "implemented_in", "it-a", "it/engine")
    kbwrite.upsert_component(tx, ROOT, "it-engine", "service", None)
    kbwrite.link(tx, ROOT, "describes", "it-b", "it-engine")
    kbwrite.link(tx, ROOT, "implemented_in", "it-engine", "it/engine")
    assert kbwrite.unlink(tx, ROOT, "implemented_in", "it-engine", "it/engine")["removed"] == 1
    assert kbwrite.unlink(tx, ROOT, "describes", "it-b", "it-engine")["removed"] == 1
    assert kb.read_related(tx, ROOT, "it-b")["components"] == []
