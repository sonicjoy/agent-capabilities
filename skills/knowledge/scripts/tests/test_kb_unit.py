"""Unit tests for kb.py: no database needed. Run: python -m pytest skills/knowledge/scripts/tests"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kb  # noqa: E402

ROOT = kb.repo_root()


@pytest.fixture(autouse=True)
def no_registry(monkeypatch):
    """Unit tests must not see the developer's real Windows user environment."""
    monkeypatch.setattr(kb, "_windows_user_env", lambda name: None)
    for key in kb.ENV_KEYS + kb.READER_KEYS + ("COLOSSUS_KB_REPO",):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------- statement splitting

def test_split_statements_drops_comment_only_chunks_and_keeps_inline_semicolons():
    text = "// header\nCREATE (a);\n// between\nMATCH (n) WHERE n.x = 'a;b'\nRETURN n;  // trailing comment\n// end\n"
    assert kb.split_statements(text) == ["CREATE (a)", "MATCH (n) WHERE n.x = 'a;b'\nRETURN n"]


def test_split_statements_handles_crlf():
    assert kb.split_statements("CREATE (a);\r\nCREATE (b);\r\n") == ["CREATE (a)", "CREATE (b)"]


# ---------------------------------------------------------------- integrity file

def test_parse_checks_rejects_duplicate_names():
    with pytest.raises(kb.KbError):
        kb.parse_checks("// check: a\nRETURN 1;\n// check: a\nRETURN 2;\n")


def test_repo_integrity_checks_are_well_formed():
    checks = kb.parse_checks((ROOT / "graph/schema/integrity.cypher").read_text(encoding="utf-8"))
    assert len(checks) == 25
    for name, query in checks:
        assert re.search(rf"RETURN '{re.escape(name)}' AS check,", query), f"{name}: RETURN must label rows with its own name"
        assert " AS detail" in query, name
        assert not re.search(r"\b(CREATE|MERGE|SET|DELETE|REMOVE)\b", re.sub(r"//[^\n]*", "", query)), f"{name} must be read-only"
        for label in re.findall(r"\(\w*:(\w+)", query):
            assert label.startswith("Kb"), f"{name}: label {label} is not a KB label"
        for rel in re.findall(r"\[\w*:(\w+)", query):
            assert rel.startswith("KB_"), f"{name}: relationship {rel} is not a KB type"


# ---------------------------------------------------------------- migrations

def test_repo_migrations_load_in_order_with_kb_names_only():
    migrations = kb.load_migrations(ROOT)
    assert [m.id[:3] for m in migrations] == sorted(m.id[:3] for m in migrations)
    assert migrations[0].id == "001_constraints"
    for m in migrations:
        for st in kb.split_statements(m.text):
            for name in re.findall(r"(?:CONSTRAINT|INDEX)\s+(\w+)\s", st):
                if name not in ("IF",):
                    assert name.startswith("kb_"), f"{m.id}: {name}"
            for label in re.findall(r"\(\w*:(\w+)", st):
                assert label.startswith("Kb"), f"{m.id}: {label}"


def test_checksum_ignores_line_endings():
    lf = kb.Migration("001_x", Path("x"), "CREATE (a);\n")
    crlf = kb.Migration("001_x", Path("x"), "CREATE (a);\r\n")
    assert lf.checksum == crlf.checksum


def _m(mid, text="CREATE (a);"):
    return kb.Migration(mid, Path(mid), text)


def test_plan_migrations_returns_pending_in_order():
    ms = [_m("001_a"), _m("002_b"), _m("003_c")]
    assert [m.id for m in kb.plan_migrations(ms, {"001_a": ms[0].checksum})] == ["002_b", "003_c"]


def test_plan_migrations_refuses_edited_migration():
    ms = [_m("001_a")]
    with pytest.raises(kb.KbError, match="edited"):
        kb.plan_migrations(ms, {"001_a": "different"})


def test_plan_migrations_refuses_unknown_applied_migration():
    with pytest.raises(kb.KbError, match="doesn't"):
        kb.plan_migrations([_m("001_a")], {"001_a": _m("001_a").checksum, "009_newer": "x"})


def test_load_migrations_refuses_duplicate_numbers(tmp_path):
    (tmp_path / "graph/migrations").mkdir(parents=True)
    (tmp_path / "graph/migrations/001_a.cypher").write_text("CREATE (a);")
    (tmp_path / "graph/migrations/001_b.cypher").write_text("CREATE (b);")
    with pytest.raises(kb.KbError, match="share a number"):
        kb.load_migrations(tmp_path)


# ---------------------------------------------------------------- templates

@pytest.mark.parametrize("name", ["../secrets", "Search", "a-b", "", "x/y", "1abc"])
def test_load_template_rejects_unsafe_names(name):
    with pytest.raises(kb.KbError, match="invalid template"):
        kb.load_template(ROOT, "read", name)


def test_load_template_rejects_unknown_kind():
    with pytest.raises(kb.KbError, match="invalid template"):
        kb.load_template(ROOT, "admin", "create_kb_users")


def test_load_template_requires_one_statement(tmp_path):
    (tmp_path / "graph/queries/read").mkdir(parents=True)
    (tmp_path / "graph/queries/read/two.cypher").write_text("// two\nMATCH (n) RETURN n;\nMATCH (m) RETURN m;\n")
    (tmp_path / "graph/queries/read/one.cypher").write_text("// one\nMATCH (n) RETURN n;\n")
    with pytest.raises(kb.KbError, match="exactly one"):
        kb.load_template(tmp_path, "read", "two")
    assert kb.load_template(tmp_path, "read", "one") == "MATCH (n) RETURN n"


# ---------------------------------------------------------------- configuration

def test_writer_connection_lists_missing_settings():
    with pytest.raises(kb.KbError, match="COLOSSUS_KB_URI, COLOSSUS_KB_USER, COLOSSUS_KB_PASSWORD, COLOSSUS_KB_DATABASE"):
        kb.writer_connection()


def _set_writer(monkeypatch, host="839b9d82.databases.neo4j.io"):
    monkeypatch.setenv("COLOSSUS_KB_URI", f"neo4j+s://{host}")
    monkeypatch.setenv("COLOSSUS_KB_USER", "kb_writer")
    monkeypatch.setenv("COLOSSUS_KB_PASSWORD", "pw")
    monkeypatch.setenv("COLOSSUS_KB_DATABASE", "neo4j")


def test_writer_connection_describe_has_no_password(monkeypatch):
    _set_writer(monkeypatch)
    conn = kb.writer_connection()
    assert conn.describe() == "kb_writer@839b9d82.databases.neo4j.io/neo4j (COLOSSUS_KB_* from environment)"
    assert "pw" not in conn.describe() and "pw" not in repr(conn)


def test_writer_connection_reports_registry_origin(monkeypatch):
    values = {"COLOSSUS_KB_URI": "neo4j+s://h", "COLOSSUS_KB_USER": "u", "COLOSSUS_KB_PASSWORD": "secret",
              "COLOSSUS_KB_DATABASE": "neo4j"}
    monkeypatch.setattr(kb, "_windows_user_env", values.get)
    monkeypatch.setenv("COLOSSUS_KB_USER", "")  # empty counts as unset: the registry value is used
    conn = kb.writer_connection()
    assert conn.user == "u" and conn.source == "COLOSSUS_KB_* from Windows user registry"


def test_main_reports_configuration_errors_without_traceback(capsys):
    assert kb.main(["status"]) == 2
    assert "missing COLOSSUS_KB_URI" in capsys.readouterr().err


def test_run_integrity_uses_one_read_transaction():
    calls = []

    class FakeTx:
        def run(self, query):
            return [{"detail": "x"}] if "'multiple_current' AS check" in query else []

    class FakeSession:
        def execute_read(self, fn, *args):
            calls.append("read")
            return fn(FakeTx(), *args)

        def run(self, *a, **k):
            raise AssertionError("integrity must not run checks outside execute_read")

    n, problems = kb.run_integrity(FakeSession(), ROOT)
    assert calls == ["read"] and n == 25
    assert problems == [{"check": "multiple_current", "detail": "x"}]


def _set_reader(monkeypatch):
    monkeypatch.setenv("COLOSSUS_KB_READER_USER", "kb_reader")
    monkeypatch.setenv("COLOSSUS_KB_READER_PASSWORD", "reader-pw")


def test_reader_connection_prefers_the_reader_login(monkeypatch):
    _set_writer(monkeypatch)
    _set_reader(monkeypatch)
    conn = kb.reader_connection()
    assert (conn.user, conn.password, conn.database) == ("kb_reader", "reader-pw", "neo4j")
    assert conn.source == "COLOSSUS_KB_READER_* from environment" and "reader-pw" not in repr(conn)


def test_reader_connection_works_without_any_writer_password(monkeypatch):
    monkeypatch.setenv("COLOSSUS_KB_URI", "neo4j+s://839b9d82.databases.neo4j.io")
    monkeypatch.setenv("COLOSSUS_KB_DATABASE", "neo4j")
    _set_reader(monkeypatch)
    assert kb.reader_connection().user == "kb_reader"
    with pytest.raises(kb.KbError, match="COLOSSUS_KB_USER, COLOSSUS_KB_PASSWORD"):
        kb.writer_connection()


def test_reader_connection_falls_back_to_the_writer(monkeypatch):
    _set_writer(monkeypatch)
    assert kb.reader_connection().user == "kb_writer"


def test_reader_connection_needs_uri_and_database(monkeypatch):
    _set_reader(monkeypatch)
    with pytest.raises(kb.KbError, match="COLOSSUS_KB_URI, COLOSSUS_KB_DATABASE"):
        kb.reader_connection()


def test_kb_has_no_admin_commands_and_never_reads_cursor_config(capsys):
    with pytest.raises(SystemExit):
        kb.main(["migrate"])
    source = Path(kb.__file__).read_text(encoding="utf-8")
    assert "mcp.json" not in source and "ADMIN" not in source


def test_output_is_utf8_whatever_the_console_code_page(tmp_path):
    """Windows pipes default to cp1252: facts with curly quotes or dashes printed garbled (or not at all)."""
    import subprocess
    text = "“leg is settled” — é"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    code = f"import sys; sys.path.insert(0, {str(Path(kb.__file__).parent)!r}); import kb; kb.utf8_output(); print({text!r})"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, check=True).stdout
    assert out.decode("utf-8").strip() == text


@pytest.mark.parametrize("script", ["kb", "export", "ingest"])
def test_every_script_main_switches_to_utf8(monkeypatch, script):
    import importlib.util
    calls = []
    monkeypatch.setattr(kb, "utf8_output", lambda: calls.append(script))
    if script == "kb":
        main = kb.main
    else:
        path = {"export": "export/graph_to_markdown.py", "ingest": "ingest/markdown_to_graph.py"}[script]
        spec = importlib.util.spec_from_file_location(f"kb_{script}_utf8", kb.repo_root() / path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        main = module.main
    with pytest.raises(SystemExit):
        main(["--help"])
    assert calls == [script]




def _no_session_marks(monkeypatch):
    for name in ("KB_IT", "COLOSSUS_KB_PASSWORD", "COLOSSUS_KB_USER", "COLOSSUS_KB_READER_USER",
                 "COLOSSUS_KB_READER_PASSWORD", "COLOSSUS_KB_FREEZE"):
        monkeypatch.delenv(name, raising=False)


def test_stale_settings_names_what_changed_since_the_app_started(monkeypatch, capsys):
    saved = {"COLOSSUS_KB_URI": "neo4j+s://fc801360.databases.neo4j.io", "COLOSSUS_KB_DATABASE": "neo4j"}
    monkeypatch.setattr(kb, "_windows_user_env", lambda name: saved.get(name))
    monkeypatch.setattr(kb.sys, "platform", "win32")
    _no_session_marks(monkeypatch)
    monkeypatch.setenv("COLOSSUS_KB_URI", "neo4j+s://other.databases.neo4j.io")       # from before the switch
    monkeypatch.setenv("COLOSSUS_KB_DATABASE", "neo4j")                               # unchanged
    monkeypatch.setenv("COLOSSUS_KB_FREEZE", "1")                                      # removed from saved since
    assert kb.stale_settings() == ["COLOSSUS_KB_URI", "COLOSSUS_KB_FREEZE"]
    assert kb.warn_settings() == ["COLOSSUS_KB_URI", "COLOSSUS_KB_FREEZE"]
    err = capsys.readouterr().err
    assert "started before COLOSSUS_KB_URI, COLOSSUS_KB_FREEZE changed" in err and "restart" in err
    assert "on purpose" in err and "fc801360" not in err and "other" not in err          # names only, no values
    monkeypatch.setenv("COLOSSUS_KB_URI", saved["COLOSSUS_KB_URI"])
    monkeypatch.delenv("COLOSSUS_KB_FREEZE")
    assert kb.stale_settings() == [] and kb.warn_settings() == [] and capsys.readouterr().err == ""
    monkeypatch.setattr(kb.sys, "platform", "linux")                                  # no saved settings to compare
    monkeypatch.setenv("COLOSSUS_KB_URI", "neo4j+s://other.databases.neo4j.io")
    assert kb.stale_settings() == []


def test_integration_test_sessions_point_at_staging_on_purpose(monkeypatch, capsys):
    monkeypatch.setattr(kb, "_windows_user_env", lambda name: "neo4j+s://fc801360.databases.neo4j.io")
    monkeypatch.setattr(kb.sys, "platform", "win32")
    _no_session_marks(monkeypatch)
    monkeypatch.setenv("COLOSSUS_KB_URI", "neo4j+s://839b9d82.databases.neo4j.io")
    monkeypatch.setenv("KB_IT", "1")
    assert kb.warn_settings() == [] and capsys.readouterr().err == ""


def test_a_uri_on_retired_staging_is_called_out(monkeypatch, capsys):
    monkeypatch.setattr(kb, "_windows_user_env", lambda name: None)
    monkeypatch.setattr(kb.sys, "platform", "linux")
    _no_session_marks(monkeypatch)
    monkeypatch.setenv("COLOSSUS_KB_URI", "neo4j+s://839b9d82.databases.neo4j.io")
    kb.warn_settings()
    err = capsys.readouterr().err
    assert "points at 839b9d82.databases.neo4j.io" in err and "setup_kb.py --reset" in err and "production" in err
    assert kb.retired_host("neo4j+s://FC801360.databases.neo4j.io") is None and kb.retired_host(None) is None


class _TTY:
    def isatty(self):
        return True


def _keys(monkeypatch, keys):
    """Type `keys` into kb.read_secret as if at a Windows console."""
    import types
    stream = iter(keys)
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getwch=lambda: next(stream)))
    monkeypatch.setattr(kb.sys, "platform", "win32")
    monkeypatch.setattr(kb.sys, "stdin", _TTY())


def test_read_secret_echoes_a_star_per_character_and_never_the_password(monkeypatch, capsys):
    _keys(monkeypatch, "s3cret-pass\r")
    assert kb.read_secret("Reader password: ") == "s3cret-pass"
    out = capsys.readouterr().out
    assert out == "Reader password: " + "*" * 11 + "\n" and "s3cret" not in out


def test_read_secret_backspace_and_special_keys(monkeypatch, capsys):
    _keys(monkeypatch, "abX\x08c\xe0K\x08\x08d\r")       # X, Backspace, c, Left arrow, Backspace x2, d
    assert kb.read_secret("> ") == "ad"
    assert capsys.readouterr().out == "> ***\b \b*\b \b\b \b*\n"
    _keys(monkeypatch, "\x08\x08ok\n")                     # Backspace on empty input does nothing
    assert kb.read_secret("> ") == "ok"


def test_read_secret_ctrl_c_cancels(monkeypatch):
    _keys(monkeypatch, "ab\x03")
    with pytest.raises(KeyboardInterrupt):
        kb.read_secret("> ")


def test_read_secret_without_a_terminal_reads_hidden_input(monkeypatch):
    import getpass
    monkeypatch.setattr(kb.sys, "stdin", type("Pipe", (), {"isatty": lambda self: False})())
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "piped")
    assert kb.read_secret("> ") == "piped"


def test_parse_instant_accepts_a_trailing_z_on_any_python():
    """Python 3.10's fromisoformat rejects 'Z', and the error message itself suggests a Z example (!21 review)."""
    from datetime import datetime, timezone
    expected = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    assert kb.parse_instant("2026-03-01T12:00:00Z") == expected == kb.parse_instant("2026-03-01T12:00:00z")
    assert kb.parse_instant("2026-03-01T12:00:00+00:00") == expected
    assert kb.parse_instant("2026-03-01") == datetime(2026, 3, 1, tzinfo=timezone.utc)
