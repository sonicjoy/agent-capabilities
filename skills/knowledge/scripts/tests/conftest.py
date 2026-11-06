"""Shared test setup. Integration fixtures connect only to a test KB (a local Neo4j, or the old staging instance),
and every test transaction is rolled back."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kb  # noqa: E402

STAGING_HOST = "839b9d82.databases.neo4j.io"
# Staging is retired (2026-10-08); integration tests now run on a local Neo4j Enterprise container (scripts README).
TEST_HOSTS = {STAGING_HOST, "localhost", "127.0.0.1"}
ROOT = kb.repo_root()

# search_text exactly as the write template and the stale_search_text check build it.
SEARCH = ("toLower(v.title + '\\n' + v.summary + '\\n' + reduce(acc = '', k IN coalesce(v.keywords, []) | "
          "acc + CASE acc WHEN '' THEN '' ELSE ' ' END + k) + '\\n' + v.statement)")
# A well-formed version body; tests override single properties with `props`.
V = ("title: 'T', summary: 'S', statement: 'B', keywords: ['k'], kind: 'rule', status: 'active', change_type: 'create', "
     "valid_from: datetime() - duration('P2D'), recorded_at: datetime() - duration('P1D'), source_type: 'test', "
     "source_refs: ['it'], confidence: 'inferred', via: 'agent'")
IT_PERSON = "it@colossusbets.com"


def integration_enabled() -> bool:
    return os.environ.get("KB_IT") == "1"


@pytest.fixture(scope="module")
def session():
    if not integration_enabled():
        pytest.skip("set KB_IT=1 to run against KB staging")
    conn = kb.writer_connection()
    if conn.host not in TEST_HOSTS:
        pytest.fail(f"integration tests only run against a test KB ({', '.join(sorted(TEST_HOSTS))}), not {conn.host}")
    with kb.driver(conn) as drv, drv.session(database=conn.database) as s:
        yield s


@pytest.fixture
def tx(session):
    t = session.begin_transaction()
    yield t
    t.rollback()


def new_fact(tx, fid, category="business/pools"):
    tx.run("MATCH (c:KbCategory {path: $category}) "
           "MERGE (p:KbPerson {email: $person}) ON CREATE SET p.name = 'IT' "
           "CREATE (:KbFact {id: $fid, created_at: datetime()})-[:KB_IN_CATEGORY]->(c)",
           fid=fid, category=category, person=IT_PERSON).consume()


def add_version(tx, fid, vid, props, current=False):
    """A version of fact `fid` with author, V's defaults overridden by `props`, and search_text built in Cypher."""
    label = ":KbFactVersion:KbCurrent" if current else ":KbFactVersion"
    tx.run(f"MATCH (f:KbFact {{id: $fid}}), (p:KbPerson {{email: $person}}) "
           f"CREATE (f)-[:KB_HAS_VERSION]->(v{label} {{version_id: $vid, {V}}})-[:KB_AUTHORED_BY]->(p) "
           f"SET v += $props SET v.search_text = {SEARCH}", fid=fid, vid=vid, person=IT_PERSON, props=props).consume()


def good_fact(tx, fid, category="business/pools"):
    """A fact with one current, well-formed version `<fid>-v1`."""
    new_fact(tx, fid, category)
    add_version(tx, fid, f"{fid}-v1", {}, current=True)


def supersede(tx, new_vid, old_vid):
    tx.run("MATCH (n:KbFactVersion {version_id: $n}), (o:KbFactVersion {version_id: $o}) CREATE (n)-[:KB_SUPERSEDES]->(o)",
           n=new_vid, o=old_vid).consume()


def it_search(tx, q):
    """The search template's ranking, restricted to test facts (ids starting with 'it-'). Staging holds the real KB
    since #9, which would otherwise crowd test facts out of the 8-result limit."""
    rows = kb.read_rows(tx, ROOT, "search", words=kb.search_words(q), limit=500)
    return [r for r in rows if r["id"].startswith("it-")]
