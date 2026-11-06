"""Integration tests against the KB staging instance. Every write runs in a transaction that is rolled back.

Opt in with KB_IT=1 and the COLOSSUS_KB_* settings for kb_writer. Refuses any host but staging (see conftest.py).
Run: KB_IT=1 python -m pytest skills/knowledge/scripts/tests
"""
from datetime import datetime, timedelta, timezone

import pytest

import kb
from conftest import ROOT, SEARCH, V, add_version, good_fact, integration_enabled, supersede


def _window(start_days_ago, end_days_ago):
    """Business-time props for an older version that ends before a good_fact's v1 starts (2 days ago)."""
    now = datetime.now(timezone.utc)
    return {"valid_from": now - timedelta(days=start_days_ago), "valid_to": now - timedelta(days=end_days_ago)}

pytestmark = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")

CHECKS = dict(kb.integrity_checks(ROOT))


def problems(tx):
    return {(c, d) for c, q in CHECKS.items() for d in (r["detail"] for r in tx.run(q))}


# One fixture per check. Each builds a broken structure on top of a well-formed fact (or alone).
def fx_multiple_current(tx):
    good_fact(tx, "it-a"); add_version(tx, "it-a", "it-a-v2", {}, current=True)

def fx_current_not_open_active(tx):
    good_fact(tx, "it-a"); tx.run("MATCH (v:KbCurrent {version_id: 'it-a-v1'}) SET v.valid_to = datetime()").consume()

def fx_active_not_current(tx):
    good_fact(tx, "it-a"); add_version(tx, "it-a", "it-a-v2", {})  # a second active version without :KbCurrent

def fx_closed_without_recorded_to(tx):
    good_fact(tx, "it-a"); add_version(tx, "it-a", "it-a-v0", {**_window(10, 3), "status": "superseded"})
    tx.run("MATCH (n {version_id: 'it-a-v1'}), (o {version_id: 'it-a-v0'}) CREATE (n)-[:KB_SUPERSEDES]->(o)").consume()

def fx_retracted_without_valid_to(tx):
    good_fact(tx, "it-a")
    tx.run("MATCH (v:KbCurrent {version_id: 'it-a-v1'}) REMOVE v:KbCurrent SET v.status = 'retracted', v.recorded_to = datetime()").consume()

def fx_superseded_without_successor(tx):
    good_fact(tx, "it-a")
    add_version(tx, "it-a", "it-a-v0", {**_window(10, 3), "status": "superseded"})
    tx.run("MATCH (v {version_id: 'it-a-v0'}) SET v.recorded_to = datetime()").consume()

def fx_draft_closed(tx):
    good_fact(tx, "it-a"); add_version(tx, "it-a", "it-a-d", {"status": "draft"})
    tx.run("MATCH (v {version_id: 'it-a-d'}) SET v.recorded_to = datetime()").consume()

def fx_orphaned_history(tx):
    good_fact(tx, "it-a")
    tx.run("MATCH (v:KbCurrent {version_id: 'it-a-v1'}) REMOVE v:KbCurrent SET v.status = 'superseded', v.recorded_to = datetime()").consume()

def fx_fact_without_versions(tx):
    tx.run("MATCH (c:KbCategory {path: 'business/pools'}) CREATE (:KbFact {id: 'it-a', created_at: datetime()})-[:KB_IN_CATEGORY]->(c)").consume()

def fx_version_owner(tx):
    good_fact(tx, "it-a")
    tx.run(f"MATCH (p:KbPerson {{email: 'it@colossusbets.com'}}) "
           f"CREATE (v:KbFactVersion {{version_id: 'it-lonely', {V}}})-[:KB_AUTHORED_BY]->(p) "
           f"SET v.status = 'draft', v.search_text = {SEARCH}").consume()

def fx_fact_category_count(tx):
    good_fact(tx, "it-a"); tx.run("MATCH (:KbFact {id: 'it-a'})-[r:KB_IN_CATEGORY]->() DELETE r").consume()

def fx_fact_in_non_leaf_category(tx):
    good_fact(tx, "it-a")
    tx.run("MATCH (f:KbFact {id: 'it-a'})-[r:KB_IN_CATEGORY]->() DELETE r WITH f MATCH (c:KbCategory {path: 'business'}) CREATE (f)-[:KB_IN_CATEGORY]->(c)").consume()

def fx_category_outside_library(tx):
    tx.run("CREATE (:KbCategory {path: 'it/orphan', title: 'IT'})").consume()

def fx_empty_required_text(tx):
    good_fact(tx, "it-a"); tx.run(f"MATCH (v {{version_id: 'it-a-v1'}}) SET v.keywords = ['', 'x'] SET v.search_text = {SEARCH}").consume()

def fx_stale_search_text(tx):
    good_fact(tx, "it-a"); tx.run("MATCH (v {version_id: 'it-a-v1'}) SET v.title = 'Changed later'").consume()

def fx_bad_enum(tx):
    good_fact(tx, "it-a"); tx.run("MATCH (v {version_id: 'it-a-v1'}) SET v.kind = 'opinion'").consume()

def fx_business_overlap(tx):
    # v0 was replaced by v1 but still claims business time until yesterday, which overlaps v1 (from 2 days ago).
    good_fact(tx, "it-a")
    add_version(tx, "it-a", "it-a-v0", {**_window(10, 1), "status": "superseded"})
    supersede(tx, "it-a-v1", "it-a-v0")
    tx.run("MATCH (v {version_id: 'it-a-v0'}) SET v.recorded_to = datetime()").consume()

def fx_future_dated(tx):
    good_fact(tx, "it-a"); tx.run("MATCH (v {version_id: 'it-a-v1'}) SET v.valid_from = datetime() + duration('P1D')").consume()

def fx_inverted_interval(tx):
    good_fact(tx, "it-a")
    add_version(tx, "it-a", "it-a-v0", {**_window(10, 3), "status": "superseded"})
    tx.run("MATCH (n {version_id: 'it-a-v1'}), (o {version_id: 'it-a-v0'}) CREATE (n)-[:KB_SUPERSEDES]->(o) "
           "SET o.recorded_to = o.recorded_at - duration('P1D')").consume()

def fx_branching_supersedes(tx):
    # v0 is superseded by both the current v1 and a retracted x (a retraction needs no successor).
    good_fact(tx, "it-a")
    add_version(tx, "it-a", "it-a-v0", {**_window(10, 3), "status": "superseded"})
    add_version(tx, "it-a", "it-a-x", {**_window(20, 15), "status": "retracted"})
    tx.run("MATCH (o {version_id: 'it-a-v0'}), (a {version_id: 'it-a-v1'}), (b {version_id: 'it-a-x'}) "
           "CREATE (a)-[:KB_SUPERSEDES]->(o), (b)-[:KB_SUPERSEDES]->(o) "
           "SET o.recorded_to = datetime(), b.recorded_to = datetime()").consume()

def fx_supersedes_many(tx):
    good_fact(tx, "it-a")
    add_version(tx, "it-a", "it-a-o1", {**_window(10, 3), "status": "superseded"})
    add_version(tx, "it-a", "it-a-o2", {**_window(20, 15), "status": "superseded"})
    tx.run("MATCH (n {version_id: 'it-a-v1'}), (a {version_id: 'it-a-o1'}), (b {version_id: 'it-a-o2'}) "
           "CREATE (n)-[:KB_SUPERSEDES]->(a), (n)-[:KB_SUPERSEDES]->(b) "
           "SET a.recorded_to = datetime(), b.recorded_to = datetime()").consume()

def fx_draft_supersedes(tx):
    good_fact(tx, "it-a"); add_version(tx, "it-a", "it-a-d", {"status": "draft"})
    tx.run("MATCH (d {version_id: 'it-a-d'}), (c {version_id: 'it-a-v1'}) CREATE (d)-[:KB_SUPERSEDES]->(c)").consume()

def fx_supersedes_across_facts(tx):
    good_fact(tx, "it-a"); good_fact(tx, "it-b")
    tx.run("MATCH (a {version_id: 'it-a-v1'}), (b {version_id: 'it-b-v1'}) CREATE (a)-[:KB_SUPERSEDES]->(b)").consume()

def fx_missing_author(tx):
    good_fact(tx, "it-a"); tx.run("MATCH ({version_id: 'it-a-v1'})-[r:KB_AUTHORED_BY]->() DELETE r").consume()

def fx_bad_relates_to(tx):
    good_fact(tx, "it-a"); good_fact(tx, "it-b")
    tx.run("MATCH (a:KbFact {id: 'it-a'}), (b:KbFact {id: 'it-b'}) CREATE (a)-[:KB_RELATES_TO]->(b)").consume()


FIXTURES = {name[3:]: fn for name, fn in globals().items() if name.startswith("fx_")}

# Checks a fixture may fire besides its own, because the overlap can't be avoided. A history with no current version
# and no final retraction must end in a superseded version with no successor, so orphaned_history always comes with
# superseded_without_successor.
ALSO_FIRES = {"orphaned_history": {"superseded_without_successor"},
              # two open-ended active versions of one fact always overlap in business time
              "multiple_current": {"business_overlap"}, "active_not_current": {"business_overlap"}}


def test_every_check_has_a_fixture():
    assert set(FIXTURES) == set(CHECKS)


def test_staging_is_clean_and_fully_migrated(session):
    assert kb.run_integrity(session, ROOT) == (25, [])
    applied = kb.applied_migrations(session)
    assert kb.plan_migrations(kb.load_migrations(ROOT), applied) == []


def test_cli_status_and_integrity(capsys):
    assert kb.main(["status"]) == 0
    out = capsys.readouterr().out
    expected = kb.reader_connection().user           # kb_reader when COLOSSUS_KB_READER_* is set, else kb_writer
    assert f'"user": "{expected}"' in out and '"migrations_pending": []' in out and '"categories": 30' in out
    assert kb.main(["integrity"]) == 0
    assert "clean (25 checks)" in capsys.readouterr().out


def test_well_formed_fact_passes_every_check(tx):
    good_fact(tx, "it-good")
    add_version(tx, "it-good", "it-good-d", {"status": "draft"})  # an open draft is allowed
    assert problems(tx) == set()


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_fixture_triggers_exactly_its_check(tx, check):
    FIXTURES[check](tx)
    fired = {c for c, _ in problems(tx)}
    assert fired == {check} | ALSO_FIRES.get(check, set()), f"{check} fixture fired {sorted(fired)}"


class _WriteAccepted(Exception):
    pass


def test_read_transactions_refuse_writes(session):
    """What run_integrity relies on: the server refuses a write inside execute_read. If it ever accepted one, the
    sentinel exception makes execute_read roll back, so nothing is committed to staging either way."""
    def attempt(tx):
        tx.run("CREATE (:KbFact {id: 'it-readonly', created_at: datetime()})").consume()
        raise _WriteAccepted()

    with pytest.raises(Exception) as err:
        session.execute_read(attempt)
    assert not isinstance(err.value, _WriteAccepted), "the server accepted a write in a read transaction"
    assert getattr(err.value, "code", None) == "Neo.ClientError.Statement.AccessMode"
