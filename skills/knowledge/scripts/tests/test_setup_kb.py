"""Tests for scripts/setup_kb.py, the one-command KB setup. No database, no real config files."""
import importlib.util
import json
import sys
from pathlib import Path

from conftest import ROOT

_spec = importlib.util.spec_from_file_location("kb_setup", ROOT / "scripts" / "setup_kb.py")
setup = importlib.util.module_from_spec(_spec)
sys.modules["kb_setup"] = setup
_spec.loader.exec_module(setup)


def test_the_mcp_server_is_read_only_and_holds_no_secret():
    cursor = setup.cursor_server()
    assert "--read-only" in cursor["args"] and cursor["env"]["NEO4J_USERNAME"] == "${env:COLOSSUS_KB_READER_USER}"
    assert all(v.startswith("${env:") for v in cursor["env"].values())
    claude = setup.claude_add_args()
    assert claude[:5] == ["mcp", "add", "neo4j-colossus-kb", "--scope", "user"] and claude[-1] == "--read-only"
    assert "NEO4J_PASSWORD=${COLOSSUS_KB_READER_PASSWORD}" in claude


def test_the_example_config_matches_what_setup_installs():
    example = json.loads((ROOT / "mcp" / "mcp.example.json").read_text(encoding="utf-8"))["mcpServers"]
    assert example["neo4j-colossus-kb"] == setup.cursor_server()


def test_merge_into_cursor_config_adds_once_and_keeps_other_servers():
    cfg = {"mcpServers": {"neo4j-aura": {"command": "uvx"}}}
    assert setup.merge_cursor(cfg) is True and setup.merge_cursor(cfg) is False
    assert set(cfg["mcpServers"]) == {"neo4j-aura", "neo4j-colossus-kb"}
    empty = {}
    assert setup.merge_cursor(empty) and "neo4j-colossus-kb" in empty["mcpServers"]


def test_settings_to_ask_skips_set_ones_and_the_writer_for_reader_only():
    current = {"COLOSSUS_KB_URI": "x", "COLOSSUS_KB_DATABASE": "neo4j"}.get
    names = lambda todo: [t[0] for t in todo]
    assert names(setup.settings_to_ask(True, False, current)) == ["COLOSSUS_KB_READER_USER",
                                                                   "COLOSSUS_KB_READER_PASSWORD"]
    assert "COLOSSUS_KB_PASSWORD" in names(setup.settings_to_ask(False, False, current))
    assert len(setup.settings_to_ask(False, True, current)) == len(setup.SETTINGS)    # --reset asks for all
    assert all(secret for name, _, _, secret, _ in setup.SETTINGS if name.endswith("PASSWORD"))


def test_never_sets_up_the_admin_login():
    assert not [s for s in setup.SETTINGS if "ADMIN" in s[0] or s[2] == "neo4j" and s[0].endswith("USER")]
    assert "neo4j" not in setup.cursor_server()["env"].values()


def test_link_reports_existing_links_and_foreign_folders(tmp_path):
    target = tmp_path / "skill"
    target.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    assert setup.link(target, other, dry_run=False).startswith("skip")
    assert setup.link(target, tmp_path / "new", dry_run=True) == "[dry-run] link"
    assert setup.link(target, tmp_path / "new", dry_run=False) == "linked"
    assert setup.link(target, tmp_path / "new", dry_run=False) == "ok"


def test_logins_are_per_person_with_no_shared_default():
    """Each person types their own kb_<name> / kb_<name>_reader (#20); the shared logins are never offered."""
    defaults = dict((s[0], s[2]) for s in setup.SETTINGS)
    assert defaults["COLOSSUS_KB_USER"] is None and defaults["COLOSSUS_KB_READER_USER"] is None


def test_shared_logins_are_never_kept(monkeypatch):
    """--reset + Enter must not keep kb_reader/kb_writer, and a plain run asks again for a shared login and its
    password (the same trap as the staging URI in !14)."""
    answers = iter(["", "kb_alberto"])            # Enter is refused (no current, no default), then a real login
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert setup.ask("Your writer login (kb_<name>)", None, False, "kb_writer") == "kb_alberto"
    current = {"COLOSSUS_KB_URI": "neo4j+s://fc801360.databases.neo4j.io", "COLOSSUS_KB_DATABASE": "neo4j",
               "COLOSSUS_KB_READER_USER": "kb_alberto_reader", "COLOSSUS_KB_READER_PASSWORD": "x",
               "COLOSSUS_KB_USER": "kb_writer", "COLOSSUS_KB_PASSWORD": "x"}
    assert [s[0] for s in setup.settings_to_ask(False, False, current.get)] == ["COLOSSUS_KB_USER", "COLOSSUS_KB_PASSWORD"]
    assert setup.settings_to_ask(True, False, current.get) == []          # reader-only: the writer isn't asked


def test_new_machines_default_to_production():
    assert dict((s[0], s[2]) for s in setup.SETTINGS)["COLOSSUS_KB_URI"] == "neo4j+s://fc801360.databases.neo4j.io"


def test_reset_answered_with_enter_keeps_the_current_values(monkeypatch):
    """Enter on --reset must not fall back to a default and move a machine to another instance."""
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(setup.kb, "read_secret", lambda prompt: "")
    assert setup.ask("KB URI", "neo4j+s://default", False, "neo4j+s://current") == "neo4j+s://current"
    assert setup.ask("KB URI", "neo4j+s://default", False, None) == "neo4j+s://default"
    assert setup.ask("Reader password", None, True, "current-secret") == "current-secret"
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "neo4j+s://typed")
    assert setup.ask("KB URI", "neo4j+s://default", False, "neo4j+s://current") == "neo4j+s://typed"
    assert "[neo4j+s://current]" in prompts[0]


def test_a_password_prompt_never_shows_the_current_password(monkeypatch):
    prompts = []
    monkeypatch.setattr(setup.kb, "read_secret", lambda prompt: prompts.append(prompt) or "")
    setup.ask("Writer password", None, True, "s3cret-value")
    assert "s3cret-value" not in prompts[0] and "Enter keeps the current one" in prompts[0]


# ---------------------------------------------------------------- one-time setup and --check

def test_claude_md_import_is_added_once_and_a_managed_block_is_respected(tmp_path):
    md = tmp_path / ".claude" / "CLAUDE.md"
    assert setup.ensure_claude_md(md, dry_run=True) == "[dry-run] add the import" and not md.exists()
    assert setup.ensure_claude_md(md, dry_run=False) == "added"
    assert setup.claude_import() in md.read_text(encoding="utf-8")
    assert setup.ensure_claude_md(md, dry_run=False) == "ok"                       # idempotent
    md.write_text("# mine\n\n" + setup.CLAUDE_BEGIN + "\n@C:/elsewhere/claude/CLAUDE.md\n" + setup.CLAUDE_END + "\n",
                  encoding="utf-8")
    assert setup.ensure_claude_md(md, dry_run=False).startswith("skip") and "# mine" in md.read_text(encoding="utf-8")


def test_cursor_rules_are_asked_for_once_per_version(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup, "copy_to_clipboard", lambda text: True)
    monkeypatch.setattr(setup, "ensure_claude_md", lambda path, dry_run: "ok")
    args = type("A", (), {"dry_run": False})()
    answers = iter(["n", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    setup.setup_instructions(args, home=tmp_path)
    assert "not yet" in capsys.readouterr().out
    setup.setup_instructions(args, home=tmp_path)
    assert "won't be asked again" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt: (_ for _ in ()).throw(AssertionError("asked again")))
    setup.setup_instructions(args, home=tmp_path)
    assert "already pasted" in capsys.readouterr().out
    monkeypatch.setattr(setup, "rules_fingerprint", lambda: "changed-rules")          # the rules changed
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    setup.setup_instructions(args, home=tmp_path)
    assert "won't be asked again" in capsys.readouterr().out


def test_the_clipboard_block_is_the_cursor_user_rules():
    block = setup.cursor_rules_block()
    assert block.startswith("Colossus knowledge") and "kb.py write" in block and "```" not in block


def _home(tmp_path, linked=True):
    for tool in (".claude", ".cursor"):
        (tmp_path / tool / "skills").mkdir(parents=True)
        if linked:
            setup.link(setup.ROOT / "skills" / "knowledge", tmp_path / tool / "skills" / "knowledge", dry_run=False)
    (tmp_path / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"neo4j-colossus-kb": {}}}), encoding="utf-8")
    setup.ensure_claude_md(tmp_path / ".claude" / "CLAUDE.md", dry_run=False)
    (tmp_path / ".cursor" / "colossus-kb-user-rules.sha256").write_text(setup.rules_fingerprint(), encoding="utf-8")
    return tmp_path


def _runner(status_ok=True, readonly_ok=True, writer_ok=True):
    def run(cmd, env):
        assert all(not k.startswith("COLOSSUS_KB_") or k in [s[0] for s in setup.SETTINGS] for k in env)
        if cmd[-1] == "status":
            return (0, '{"connection": "kb_reader@fc801360/neo4j (x)", "facts": 46}') if status_ok else (2, "kb.py: Unauthorized")
        if cmd[-1].endswith("check_kb_readonly.py"):
            return (0, "OK: read-only") if readonly_ok else (1, "FAILED: the database accepted a kb_reader write")
        return (0, "DRY RUN (rolled back): id=setup-check") if writer_ok else (2, "kb.py: Unauthorized")
    return run


def test_check_passes_when_everything_is_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "get_user_env", lambda name: "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/bin/uv" if name == "uv" else None)   # no claude CLI here
    results = setup.verify(reader_only=False, home=_home(tmp_path), runner=_runner())
    failed = [r[0] for r in results if not r[1]]
    assert failed == ["neo4j-colossus-kb in Claude Code"]
    assert any(r[0] == "KB reachable (kb.py status)" and "46 facts" in r[2] for r in results)


def test_check_runs_kb_scripts_the_way_agents_do(tmp_path, monkeypatch):
    """--check must run `uv run kb.py`, not the Python that ran setup: on macOS that Python had neo4j (via
    `uv run --with neo4j setup_kb.py`) while the agents' python3 didn't, and every check passed anyway (#21)."""
    monkeypatch.setattr(setup, "get_user_env", lambda name: "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/bin/uv" if name == "uv" else None)
    ran = []
    setup.verify(reader_only=False, home=_home(tmp_path), runner=lambda cmd, env: ran.append(cmd) or _runner()(cmd, env))
    assert ran and all(cmd[:3] == ["/bin/uv", "run", "--quiet"] for cmd in ran)
    assert [Path(cmd[3]).name for cmd in ran] == ["kb.py", "check_kb_readonly.py", "kb.py"]


def test_check_fails_without_uv(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "get_user_env", lambda name: "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    failed = {r[0]: r[2] for r in setup.verify(reader_only=False, home=_home(tmp_path), runner=_runner()) if not r[1]}
    assert "install uv" in failed["uv installed"]


def test_kb_scripts_declare_the_pinned_driver_inline():
    """`uv run` installs what the # /// script block says; it must match requirements.txt (the tests' pin)."""
    pin = (setup.ROOT / "skills/knowledge/scripts/requirements.txt").read_text(encoding="utf-8").split()[0]
    for script in ("skills/knowledge/scripts/kb.py", "scripts/check_kb_readonly.py", "graph/admin/kb_users.py",
                   "graph/admin/migrate.py", "graph/admin/dump.py", "graph/admin/load.py"):
        text = (setup.ROOT / script).read_text(encoding="utf-8")
        assert f'# dependencies = ["{pin}"]' in text and '# requires-python = ">=3.11"' in text, script


def test_check_names_each_broken_part(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "get_user_env", lambda name: None if name == "COLOSSUS_KB_PASSWORD" else "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    results = setup.verify(reader_only=False, home=_home(tmp_path, linked=False),
                           runner=_runner(status_ok=False, readonly_ok=False, writer_ok=False))
    failed = {r[0]: r[2] for r in results if not r[1]}
    assert failed["settings saved"] == "missing COLOSSUS_KB_PASSWORD"
    assert {"skill linked for claude", "skill linked for cursor", "KB reachable (kb.py status)",
            "read-only MCP reads, refuses writes", "writer login works (dry-run write, rolled back)"} <= set(failed)
    assert "kb_reader write" in failed["read-only MCP reads, refuses writes"]
    assert setup.report(results) == 1


def test_reader_only_check_skips_the_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "get_user_env", lambda name: None if name in ("COLOSSUS_KB_USER", "COLOSSUS_KB_PASSWORD") else "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    results = setup.verify(reader_only=True, home=_home(tmp_path), runner=_runner())
    assert not any(r[0].startswith("writer") for r in results)
    assert dict((r[0], r[1]) for r in results)["settings saved"]


def test_reset_never_offers_the_retired_staging_instance(monkeypatch, capsys):
    """A teammate still on staging who presses Enter must land on production, not stay on staging."""
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    prod, staging = "neo4j+s://fc801360.databases.neo4j.io", "neo4j+s://839b9d82.databases.neo4j.io"
    assert setup.ask("KB URI", prod, False, staging) == prod
    assert "no longer the KB" in capsys.readouterr().out
    assert setup.ask("KB URI", prod, False, prod) == prod                       # production stays production


def test_check_fails_on_a_machine_still_on_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "get_user_env", lambda name: "neo4j+s://839b9d82.databases.neo4j.io"
                        if name == "COLOSSUS_KB_URI" else "set")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    failed = {r[0]: r[2] for r in setup.verify(reader_only=False, home=_home(tmp_path), runner=_runner()) if not r[1]}
    assert "run --reset and choose production" in failed["KB URI is the current instance"]
