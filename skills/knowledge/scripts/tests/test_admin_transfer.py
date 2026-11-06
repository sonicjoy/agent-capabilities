"""Tests for graph/admin/transfer.py, dump.py and load.py (#15). The staging rehearsal runs in one rolled-back transaction
(KB_IT=1): dump the KB, delete it, load the dump, and require an identical KB, clean integrity and untouched non-KB
data before rolling everything back."""
import importlib.util
import re
import sys

import pytest
from neo4j.time import DateTime

import kb
from conftest import ROOT, add_version, integration_enabled, new_fact

sys.path.insert(0, str(ROOT / "graph" / "admin"))
import transfer  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


load = _load("kb_admin_load", "graph/admin/load.py")
dump = _load("kb_admin_dump", "graph/admin/dump.py")
it = pytest.mark.skipif(not integration_enabled(), reason="set KB_IT=1 to run against KB staging")


def _records():
    t = {"$datetime": "2026-01-10T00:00:00.000000000+00:00"}
    return [
        {"kind": "node", "label": "KbFact", "key": "f-1", "extra_labels": [], "props": {"id": "f-1", "created_at": t}},
        {"kind": "node", "label": "KbFactVersion", "key": "v-1", "extra_labels": ["KbCurrent"],
         "props": {"version_id": "v-1", "statement": "Replay oldest first.", "keywords": ["restart"]}},
        {"kind": "rel", "type": "KB_HAS_VERSION", "from": ["KbFact", "f-1"], "to": ["KbFactVersion", "v-1"], "props": {}},
    ]


# ---------------------------------------------------------------- unit

def test_datetimes_round_trip_exactly():
    value = DateTime.from_iso_format("2026-03-01T12:34:56.123456789+00:00")
    encoded = transfer.encode(value)
    assert encoded == {"$datetime": value.iso_format()} and transfer.decode(encoded) == value
    assert transfer.decode(transfer.encode(["a", "b"])) == ["a", "b"]
    with pytest.raises(transfer.TransferError, match="can't dump"):
        transfer.encode(object())


def test_summary_counts_and_checksums():
    s = transfer.summary(_records())
    assert s["labels"] == {"KbCurrent": 1, "KbFact": 1, "KbFactVersion": 1} and s["types"] == {"KB_HAS_VERSION": 1}
    changed = _records()
    changed[1]["props"]["statement"] = "Replay newest first."
    other = transfer.summary(changed)
    assert other["id_version_statement_sha256"] != s["id_version_statement_sha256"]
    assert other["records_sha256"] != s["records_sha256"]


def test_dump_file_round_trip_and_tamper_check(tmp_path):
    path = tmp_path / "kb.jsonl"
    header = transfer.write_dump(path, _records(), "839b9d82.databases.neo4j.io", "2026-10-08T00:00:00+00:00")
    assert transfer.read_dump(path) == (header, _records())
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")           # truncated
    with pytest.raises(transfer.TransferError, match="don't match the header"):
        transfer.read_dump(path)
    path.write_text('{"kind": "node"}\n', encoding="utf-8")
    with pytest.raises(transfer.TransferError, match="not a KB dump"):
        transfer.read_dump(path)


@pytest.mark.parametrize("labels", [["Decision"], ["KbFact", "Decision"], ["KbFact", "KbCategory"], ["KbCurrent"]])
def test_only_known_kb_labels_can_be_transferred(labels):
    with pytest.raises(transfer.TransferError, match="can't transfer"):
        transfer.primary_label(labels)
    assert transfer.primary_label(["KbFactVersion", "KbCurrent"]) == "KbFactVersion"


def test_differences_name_what_changed():
    a, b = _records(), _records()
    assert transfer.differences(a, b) == []
    b[1]["props"]["statement"] = "x"
    b.append({"kind": "rel", "type": "KB_RELATES_TO", "from": ["KbFact", "f-1"], "to": ["KbFact", "f-2"],
              "props": {"rel": "see_also"}})
    diff = transfer.differences(a, b)
    assert any(d.startswith("differs: ('node', 'KbFactVersion', 'v-1')") for d in diff)
    assert any(d.startswith("only in the second: ('rel', 'KB_RELATES_TO'") for d in diff)


def test_datetimes_keep_offset_or_named_zone():
    """The driver returns the same tzinfo for "Z" and the named "UTC"; the dump records which one Neo4j stored, and
    decoding gives back what the driver must send for each."""
    stored = DateTime.from_iso_format("2026-01-01T09:30:00.123456789+00:00")
    offset = transfer.decode(transfer.encode(stored))
    assert offset == stored and getattr(offset.tzinfo, "zone", None) is None          # sent as an offset
    named = transfer.decode(transfer.encode(stored, "UTC"))
    assert named == stored and named.tzinfo.zone == "UTC"                               # sent as the zone "UTC"
    london = transfer.decode(transfer.encode(stored, "Europe/London"))
    assert london == stored and london.tzinfo.zone == "Europe/London" and london.nanosecond == 123456789
    with pytest.raises(transfer.TransferError, match="lists of datetimes"):
        transfer._props({"x": [stored]}, {}, ["x"])


def test_migrations_are_not_transferred():
    assert "KbMigration" not in transfer.KEYS and "KbMigration" in transfer.NOT_TRANSFERRED


def test_load_refuses_production_without_yes_and_the_source_itself(monkeypatch, tmp_path, capsys):
    path = tmp_path / "kb.jsonl"
    transfer.write_dump(path, _records(), "839b9d82.databases.neo4j.io", "2026-10-08T00:00:00+00:00")
    monkeypatch.setattr(load.migrate, "admin_connection", lambda: kb.Connection(
        "neo4j+s://fc801360.databases.neo4j.io", "neo4j", "p", "neo4j", "session"))
    assert load.main(["--in", str(path)]) == 2 and "production: run with --dry-run first" in capsys.readouterr().err
    monkeypatch.setattr(load.migrate, "admin_connection", lambda: kb.Connection(
        "neo4j+s://839b9d82.databases.neo4j.io", "neo4j", "p", "neo4j", "session"))
    assert load.main(["--in", str(path), "--yes"]) == 2 and "comes from 839b9d82" in capsys.readouterr().err


@pytest.mark.parametrize("change,match", [
    (lambda r: r[0].update(label="Decision"), "unknown node label 'Decision'"),
    (lambda r: r[2].update(type="PART_OF"), "unknown relationship type 'PART_OF'"),
    (lambda r: r[0].update(kind="query"), "unknown record kind 'query'"),
])
def test_load_refuses_names_outside_the_allowlists_before_running_anything(change, match):
    """Labels and types are formatted into Cypher, so a file can only name the KB's own."""
    records = _records()
    change(records)

    class NoTx:
        def run(self, *a, **k):
            raise AssertionError("nothing may run")
    with pytest.raises(transfer.TransferError, match=match):
        transfer.load_records(NoTx(), records)


# ---------------------------------------------------------------- staging rehearsal (rolled back)

WIPE = "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Kb') AND NOT n:KbMigration DETACH DELETE n"
SCHEMA = re.compile(r"^\s*(CREATE|DROP)\s+(\w+\s+)?(CONSTRAINT|INDEX)\b", re.I)


def wipe_to_freshly_migrated(tx):
    """The state production is in after `migrate.py --yes` (runbook step 2): no KB data except what the migrations
    seed (003: the library and its categories, with their migration-time properties)."""
    tx.run(WIPE).consume()
    seeded = 0
    for m in kb.load_migrations(ROOT):
        for statement in kb.split_statements(m.text):
            if not SCHEMA.match(statement):            # schema statements are already in place
                tx.run(statement).consume()
                seeded += 1
    assert seeded >= 2


@it
def test_rehearsal_dump_wipe_load_gives_an_identical_kb(tx):
    records = dump.snapshot(tx)
    before = transfer.summary(records)
    outside = transfer.outside_counts(tx)
    assert before["labels"]["KbFact"] >= 46
    wipe_to_freshly_migrated(tx)
    assert tx.run("MATCH (f:KbFact) RETURN count(f) AS n").single()["n"] == 0
    assert tx.run("MATCH (c:KbCategory) RETURN count(c) AS n").single()["n"] == 30      # seeded, as on production
    counts = load.load_into(tx, records, outside)
    assert counts["KbFact"] == before["labels"]["KbFact"]
    assert transfer.summary(transfer.dump_records(tx)) == before
    assert kb.check_problems(tx, kb.integrity_checks(ROOT)) == []
    assert "withdrawn-unit-reallocation" in [h["id"] for h in kb.read_search(tx, ROOT, "withdrawn favourite")]


@it
def test_named_and_offset_zones_survive_dump_wipe_load(tx):
    """created_at/updated_at come from Cypher's datetime() (named "UTC"); kb.py writes offsets. Both, and a real named
    zone, must come back exactly as stored: compared in Cypher, which tells them apart."""
    tx.run("MATCH (c:KbCategory {path: 'business/glossary'}) "
           "SET c.it_london = datetime('2026-01-01T00:00:00.123456789[Europe/London]'), "
           "c.it_offset = datetime('2026-01-01T00:00:00Z'), c.it_named = datetime({year: 2026, timezone: 'UTC'})").consume()
    zones = "MATCH (c:KbCategory {path: 'business/glossary'}) RETURN [c.it_london.timezone, c.it_offset.timezone, "             "c.it_named.timezone, toString(c.it_london)] AS z"
    before = tx.run(zones).single()["z"]
    facts = "MATCH (f:KbFact) WITH f ORDER BY f.id LIMIT 3 RETURN collect([f.id, f.created_at.timezone, "             "f.updated_at.timezone, toString(f.created_at)]) AS z"
    facts_before = tx.run(facts).single()["z"]
    records = transfer.dump_records(tx)
    outside = transfer.outside_counts(tx)
    wipe_to_freshly_migrated(tx)
    load.load_into(tx, records, outside)
    assert tx.run(zones).single()["z"] == before == ["Europe/London", "Z", "UTC", "2026-01-01T00:00:00.123456789Z[Europe/London]"]
    assert tx.run(facts).single()["z"] == facts_before


@it
def test_loading_twice_changes_nothing(tx):
    records = dump.snapshot(tx)
    outside = transfer.outside_counts(tx)
    load.load_into(tx, records, outside)
    assert transfer.differences(records, transfer.dump_records(tx)) == []


@it
def test_load_refuses_a_target_with_other_kb_data(tx):
    records = dump.snapshot(tx)
    outside = transfer.outside_counts(tx)
    new_fact(tx, "it-extra", category="technical/conventions/code-quality")
    add_version(tx, "it-extra", "it-extra-v1", {}, current=True)
    with pytest.raises(kb.KbError, match="isn't identical to the dump"):
        load.load_into(tx, records, outside)


@it
def test_load_refuses_when_data_outside_the_kb_would_change(tx):
    records = dump.snapshot(tx)
    outside = transfer.outside_counts(tx)
    tx.run("CREATE (:ItOutsideKb)").consume()          # stands in for a load that touched another graph
    with pytest.raises(kb.KbError, match="outside the KB would change"):
        load.load_into(tx, records, outside)


# ---------------------------------------------------------------- kb_users.py (no database)

users = _load("kb_admin_users", "graph/admin/kb_users.py")


def test_kb_users_needs_yes_on_production(monkeypatch, capsys):
    monkeypatch.setattr(users.migrate, "admin_connection", lambda: kb.Connection(
        "neo4j+s://fc801360.databases.neo4j.io", "neo4j", "p", "neo4j", "session"))
    assert users.main(["suspend-writer"]) == 2 and "production: add --yes" in capsys.readouterr().err


def test_kb_users_passwords_must_match_and_be_long(monkeypatch):
    answers = iter(["correct-horse-battery", "correct-horse-batterx"])
    monkeypatch.setattr(users.kb, "read_secret", lambda prompt: next(answers))
    with pytest.raises(kb.KbError, match="didn't match"):
        users.new_password("kb_reader")
    monkeypatch.setattr(users.kb, "read_secret", lambda prompt: "short")
    with pytest.raises(kb.KbError, match="shorter than 12"):
        users.new_password("kb_reader")


class FakeSystem:
    """The system database for kb_users.run: SHOW returns `rows`; every other statement is recorded."""

    def __init__(self, rows=()):
        self.rows, self.ran = [dict(r) for r in rows], []

    def run(self, q, **p):
        if q == users.SHOW:
            return [type("Row", (), {"data": lambda self, r=r: r})() for r in self.rows]
        self.ran.append(q)
        return type("R", (), {"consume": lambda self: None})()


def test_kb_users_create_shared_logins(monkeypatch):
    monkeypatch.setattr(users, "new_password", lambda who: f"pw-for-{who}-long")
    s = FakeSystem()
    users.run("create", s)
    assert [q.split(" SET")[0] for q in s.ran] == [
        "CREATE USER kb_reader IF NOT EXISTS", "GRANT ROLE reader TO kb_reader",
        "CREATE USER kb_writer IF NOT EXISTS", "GRANT ROLE publisher TO kb_writer"]


def test_kb_users_add_two_logins_per_person_and_skip_existing(monkeypatch):
    asked = []
    monkeypatch.setattr(users, "new_password", lambda who: asked.append(who) or f"pw-for-{who}-long")
    s = FakeSystem([{"user": "kb_alberto", "roles": ["publisher", "PUBLIC"], "suspended": False}])
    users.run("add", s, ["Alberto", "manuel"])
    assert asked == ["kb_alberto_reader", "kb_manuel", "kb_manuel_reader"]      # existing kb_alberto keeps its password
    assert [q.split(" SET")[0] for q in s.ran] == [
        "GRANT ROLE publisher TO kb_alberto",                                   # granted again: repairs a half-run
        "CREATE USER kb_alberto_reader IF NOT EXISTS", "GRANT ROLE reader TO kb_alberto_reader",
        "CREATE USER kb_manuel IF NOT EXISTS", "GRANT ROLE publisher TO kb_manuel",
        "CREATE USER kb_manuel_reader IF NOT EXISTS", "GRANT ROLE reader TO kb_manuel_reader"]


def test_kb_users_add_asks_every_password_before_changing_anything(monkeypatch):
    answers = iter(["first-password-ok"])

    def new_password(who):
        return next(answers)                         # the second prompt fails (StopIteration stands in for a mistake)
    monkeypatch.setattr(users, "new_password", new_password)
    s = FakeSystem()
    with pytest.raises(StopIteration):
        users.run("add", s, ["dominik"])
    assert s.ran == []


@pytest.mark.parametrize("name", ["reader", "writer", "a", "x_reader", "o'brien", "kb_aurel", "Mehul Shah"])
def test_kb_users_rejects_bad_names(name):
    with pytest.raises(kb.KbError, match="first name"):
        users.person_logins(name)


def test_kb_users_add_and_remove_need_names(monkeypatch, capsys):
    with pytest.raises(kb.KbError, match="name at least one person"):
        users.run("add", FakeSystem(), [])
    assert users.main(["add", "kb_x"]) == 2 and "first name" in capsys.readouterr().err   # before connecting


def test_kb_users_remove_drops_both_logins(monkeypatch):
    s = FakeSystem([{"user": "kb_aurel", "roles": ["publisher"]}, {"user": "kb_aurel_reader", "roles": ["reader"]}])
    users.run("remove", s, ["aurel", "mehul"])
    assert s.ran == ["DROP USER kb_aurel IF EXISTS", "DROP USER kb_aurel_reader IF EXISTS"]


def test_kb_users_rerun_repairs_a_login_left_without_its_role(monkeypatch):
    """A run that stopped between CREATE USER and GRANT ROLE: show flags it, and add again grants it, asking nothing."""
    monkeypatch.setattr(users, "new_password", lambda who: pytest.fail(f"asked for {who}"))
    rows = [{"user": "kb_aurel", "roles": ["PUBLIC"]}, {"user": "kb_aurel_reader", "roles": ["reader", "PUBLIC"]}]
    assert users.roleless(rows) == ["kb_aurel"]
    s = FakeSystem(rows)
    users.run("add", s, ["aurel"])
    assert s.ran == ["GRANT ROLE publisher TO kb_aurel", "GRANT ROLE reader TO kb_aurel_reader"]


def test_kb_users_remove_shared_needs_a_per_person_writer_first():
    shared = [{"user": "kb_reader", "roles": ["reader"], "suspended": False},
              {"user": "kb_writer", "roles": ["publisher"], "suspended": False}]
    with pytest.raises(kb.KbError, match="no active per-person writer"):
        users.run("remove-shared", FakeSystem(shared + [{"user": "kb_mehul_reader", "roles": ["reader"]}]))
    s = FakeSystem(shared + [{"user": "kb_mehul", "roles": ["publisher"], "suspended": False}])
    users.run("remove-shared", s)
    assert s.ran == ["DROP USER kb_reader IF EXISTS", "DROP USER kb_writer IF EXISTS"]


@pytest.mark.parametrize("error, expected", [
    ("Forbidden", "joe_luo can't manage users on fc801360.databases.neo4j.io (Neo4j's admin role is needed)"),
    ("AuthError", "fc801360.databases.neo4j.io refused the login joe_luo"),
])
def test_kb_users_explains_a_login_that_cannot_manage_users(monkeypatch, capsys, error, expected):
    """A non-admin or wrong admin login gets one clear line, not a driver traceback (seen on production, #20)."""
    import contextlib
    import neo4j.exceptions
    monkeypatch.setattr(users.migrate, "admin_connection", lambda: kb.Connection(
        "neo4j+s://fc801360.databases.neo4j.io", "joe_luo", "p", "neo4j", "session"))

    class Refusing:
        def run(self, q, **p):
            raise getattr(neo4j.exceptions, error)("Permission has not been granted for SHOW USER.")

    @contextlib.contextmanager
    def driver(conn):
        yield type("D", (), {"session": lambda self, database: contextlib.nullcontext(Refusing())})()
    monkeypatch.setattr(users.kb, "driver", driver)
    assert users.main(["show"]) == 2
    err = capsys.readouterr().err
    assert expected in err and "Traceback" not in err


def test_kb_users_set_password_for_a_person_or_one_login(monkeypatch):
    asked = []
    monkeypatch.setattr(users, "new_password", lambda who: asked.append(who) or f"pw-for-{who}-long")
    rows = [{"user": u, "roles": ["publisher" if not u.endswith("reader") else "reader"]}
            for u in ("kb_alberto", "kb_alberto_reader", "kb_mehul", "kb_mehul_reader", "kb_writer")]
    s = FakeSystem(rows)
    users.run("set-password", s, ["alberto", "kb_mehul_reader", "kb_writer", "kb_alberto"])
    assert asked == ["kb_alberto", "kb_alberto_reader", "kb_mehul_reader", "kb_writer"]       # each login once
    assert s.ran == [f"ALTER USER {u} SET PASSWORD $p CHANGE NOT REQUIRED" for u in asked]


def test_kb_users_set_password_refuses_unknown_logins_before_any_prompt(monkeypatch):
    monkeypatch.setattr(users, "new_password", lambda who: pytest.fail(f"asked for {who}"))
    s = FakeSystem([{"user": "kb_alberto", "roles": ["publisher"]}])
    with pytest.raises(kb.KbError, match="no such login: kb_alberto_reader"):
        users.run("set-password", s, ["alberto"])
    assert s.ran == []


@pytest.mark.parametrize("arg", ["kb_", "kb_a", "kb_x_writer", "kb_Alberto"])
def test_kb_users_set_password_rejects_bad_targets(arg):
    with pytest.raises(kb.KbError, match="first name"):
        users.password_targets(arg)


def test_kb_users_set_password_never_targets_the_admin():
    assert users.password_targets("neo4j") == ["kb_neo4j", "kb_neo4j_reader"]     # a kb_ login, never the admin


def test_kb_users_remove_shared_is_production_only(monkeypatch, capsys):
    monkeypatch.setattr(users.migrate, "admin_connection", lambda: kb.Connection(
        "neo4j+s://839b9d82.databases.neo4j.io", "neo4j", "p", "neo4j", "session"))
    assert users.main(["remove-shared"]) == 2 and "staging keeps the shared logins" in capsys.readouterr().err


def test_kb_users_freeze_covers_every_writer_login():
    rows = [{"user": "kb_writer", "roles": ["publisher"], "suspended": False},
            {"user": "kb_mehul", "roles": ["publisher", "PUBLIC"], "suspended": False},
            {"user": "kb_mehul_reader", "roles": ["reader"], "suspended": False},
            {"user": "kb_old", "roles": ["publisher"], "suspended": True}]
    s = FakeSystem(rows)
    users.run("suspend-writer", s)
    assert s.ran == ["ALTER USER kb_mehul SET STATUS SUSPENDED", "ALTER USER kb_writer SET STATUS SUSPENDED"]
    s = FakeSystem([{**r, "suspended": r["user"] != "kb_mehul_reader"} for r in rows])
    users.run("activate-writer", s)
    assert s.ran == ["ALTER USER kb_mehul SET STATUS ACTIVE", "ALTER USER kb_old SET STATUS ACTIVE",
                     "ALTER USER kb_writer SET STATUS ACTIVE"]
