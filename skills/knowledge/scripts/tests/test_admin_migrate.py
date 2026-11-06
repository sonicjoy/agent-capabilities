"""Unit tests for graph/admin/migrate.py (no database). Run: python -m pytest skills/knowledge/scripts/tests"""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kb  # noqa: E402

ROOT = kb.repo_root()
_spec = importlib.util.spec_from_file_location("kb_admin_migrate", ROOT / "graph" / "admin" / "migrate.py")
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(kb, "_windows_user_env", lambda name: None)
    for key in kb.ENV_KEYS + (migrate.ADMIN_USER, migrate.ADMIN_PASSWORD):
        monkeypatch.delenv(key, raising=False)


def _target(monkeypatch, host="839b9d82.databases.neo4j.io"):
    monkeypatch.setenv("COLOSSUS_KB_URI", f"neo4j+s://{host}")
    monkeypatch.setenv("COLOSSUS_KB_DATABASE", "neo4j")


def test_admin_login_is_required(monkeypatch, capsys):
    _target(monkeypatch)
    assert migrate.main(["--dry-run"]) == 2
    assert "COLOSSUS_KB_ADMIN_USER, COLOSSUS_KB_ADMIN_PASSWORD" in capsys.readouterr().err


def test_admin_login_comes_from_the_session_only(monkeypatch):
    _target(monkeypatch)
    stored = {migrate.ADMIN_USER: "neo4j", migrate.ADMIN_PASSWORD: "from-registry"}
    monkeypatch.setattr(kb, "_windows_user_env", stored.get)  # a user-level value must not be picked up
    with pytest.raises(kb.KbError, match="this terminal session only"):
        migrate.admin_connection()


def test_admin_connection_uses_session_values_without_exposing_password(monkeypatch):
    _target(monkeypatch)
    monkeypatch.setenv(migrate.ADMIN_USER, "neo4j")
    monkeypatch.setenv(migrate.ADMIN_PASSWORD, "admin-pw")
    conn = migrate.admin_connection()
    assert (conn.user, conn.host, conn.database) == ("neo4j", "839b9d82.databases.neo4j.io", "neo4j")
    assert "admin-pw" not in repr(conn) and "admin-pw" not in conn.describe()


def test_production_needs_yes(monkeypatch, capsys):
    _target(monkeypatch, host="fc801360.databases.neo4j.io")
    monkeypatch.setenv(migrate.ADMIN_USER, "neo4j")
    monkeypatch.setenv(migrate.ADMIN_PASSWORD, "admin-pw")
    assert migrate.main([]) == 2
    assert "--yes" in capsys.readouterr().err


@pytest.mark.parametrize("host,prod", [("fc801360.databases.neo4j.io", True), ("FC801360.databases.neo4j.io", True),
                                       ("fc801360.production-orch-0042.neo4j.io", True),
                                       ("839b9d82.databases.neo4j.io", False), ("fc8013601.databases.neo4j.io", False)])
def test_production_is_matched_by_instance_id(host, prod):
    assert migrate.is_production(host) is prod


def test_migrate_never_reads_cursor_config():
    assert "mcp.json" not in (ROOT / "graph" / "admin" / "migrate.py").read_text(encoding="utf-8")
