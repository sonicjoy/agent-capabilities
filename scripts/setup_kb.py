#!/usr/bin/env python3
"""Set up access to the Colossus KB on this machine, for Claude Code and Cursor: one command, run once.

    python scripts/setup_kb.py               # everything below, then the checks
    python scripts/setup_kb.py --check       # only the checks; changes nothing
    python scripts/setup_kb.py --dry-run     # show what it would do
    python scripts/setup_kb.py --reader-only # look things up only: no writer login
    python scripts/setup_kb.py --reset       # new logins or instance (Enter keeps a current value)

1. Checks uv and prepares kb.py's environment: kb.py declares its dependency inline (# /// script) and always runs
   as `uv run kb.py`, so nothing is pip-installed into your Python (Homebrew Python refuses that).
2. Links the `knowledge` skill into ~/.claude/skills and ~/.cursor/skills (links: repo updates arrive by themselves).
3. Asks for any KB setting that isn't set yet (passwords echo as *) and stores them as user environment variables:
   COLOSSUS_KB_URI, _DATABASE, _READER_USER, _READER_PASSWORD, and (unless --reader-only) _USER, _PASSWORD.
   Values are never printed.
4. Adds the read-only `neo4j-colossus-kb` MCP server to Claude Code and Cursor. Both configs hold only references
   to the variables (${NAME} / ${env:NAME}), never a password. Existing servers are left alone.
5. Claude Code: makes ~/.claude/CLAUDE.md import claude/CLAUDE.md (working agreement and the KB rules), unless
   setup-claude-code.ps1 already did.
6. Cursor: copies the KB rules (cursor/user-rules.md) to the clipboard for Settings > Rules > User Rules and asks
   once; it asks again only when the rules change.
7. Checks everything with the saved settings (as a restarted app sees them): settings, skill links, MCP entries,
   the rules, a KB read, the read-only MCP refusing writes, and a dry-run write with the writer login.

Re-running is safe and needed only for new logins (--reset) or new rules.

Each person has their own logins, kb_<name> (writer) and kb_<name>_reader, created by the KB owner with
graph/admin/kb_users.py add <name>; the passwords come through the team secret store. The shared kb_reader and
kb_writer are being retired and are never offered. The instance admin login is never set up here: its password is
only typed into one terminal session for graph/admin/* (see graph/admin/README.md).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.path.realpath(__file__)).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
import kb  # noqa: E402  (standard library only at import time: safe without neo4j)

SKILLS = ("knowledge",)
SERVER = "neo4j-colossus-kb"
MCP_PACKAGE = "mcp-neo4j-cypher@0.6.0"
# (variable, prompt, default, secret, needed for reader-only)
SETTINGS = (
    ("COLOSSUS_KB_URI", "KB URI", "neo4j+s://fc801360.databases.neo4j.io", False, True),   # production since #15
    ("COLOSSUS_KB_DATABASE", "KB database", "neo4j", False, True),
    ("COLOSSUS_KB_READER_USER", "Your reader login (kb_<name>_reader)", None, False, True),   # per person (#20)
    ("COLOSSUS_KB_READER_PASSWORD", "Reader password", None, True, True),
    ("COLOSSUS_KB_USER", "Your writer login (kb_<name>)", None, False, False),
    ("COLOSSUS_KB_PASSWORD", "Writer password", None, True, False),
)
SHARED_LOGINS = ("kb_reader", "kb_writer")        # being retired (#20): --reset + Enter must not keep them
MCP_ENV = {"NEO4J_URI": "COLOSSUS_KB_URI", "NEO4J_USERNAME": "COLOSSUS_KB_READER_USER",
           "NEO4J_PASSWORD": "COLOSSUS_KB_READER_PASSWORD", "NEO4J_DATABASE": "COLOSSUS_KB_DATABASE"}
MCP_ARGS = [MCP_PACKAGE, "--transport", "stdio", "--read-only"]


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- user environment

def get_user_env(name: str) -> str | None:
    """The variable as a newly started app would see it: the user registry on Windows, else this process."""
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, name)[0] or None
        except OSError:
            pass
    return os.environ.get(name) or None


def set_user_env(name: str, value: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("not Windows")
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    # Tell running apps (Explorer, so apps started from now on) that the environment changed
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    os.environ[name] = value


def settings_to_ask(reader_only: bool, reset: bool, current) -> list[tuple]:
    """The settings to prompt for: missing ones (or all, with reset), skipping the writer for reader-only. A login
    still set to a shared kb_reader/kb_writer counts as missing, with its password."""
    shared = set()
    for user, password in (("COLOSSUS_KB_READER_USER", "COLOSSUS_KB_READER_PASSWORD"),
                           ("COLOSSUS_KB_USER", "COLOSSUS_KB_PASSWORD")):
        if current(user) in SHARED_LOGINS:
            shared |= {user, password}
    return [s for s in SETTINGS if (s[4] or not reader_only) and (reset or not current(s[0]) or s[0] in shared)]


def ask(prompt: str, default: str | None, secret: bool, current: str | None = None) -> str:
    """A setting from the user. Enter keeps the current value (shown, unless secret), else takes the default, so a
    --reset answered with Enter changes nothing."""
    retired = None if secret else kb.retired_host(current)
    if retired:            # never offer a retired KB instance (e.g. staging after the move to production)
        say(f"  (your current {prompt}, {current}, is {retired}: Enter now takes {default})")
        current = None
    if not secret and current in SHARED_LOGINS:     # never keep a shared login (#20)
        say(f"  (the shared login {current} is being retired: enter your own kb_<name> login)")
        current = None
    while True:
        if secret:
            value = kb.read_secret(f"  {prompt} (shown as *" + ("; Enter keeps the current one" if current else "")
                                    + "): ") or (current or "")
        else:
            shown = current or default
            value = input(f"  {prompt}" + (f" [{shown}]" if shown else "") + ": ").strip() or (shown or "")
        if value:
            return value
        say("  (required)")


def setup_env(args) -> None:
    say("\n[3/7] KB settings (user environment variables)")
    todo = settings_to_ask(args.reader_only, args.reset, get_user_env)
    for name, *_ in SETTINGS:
        if name not in [t[0] for t in todo] and get_user_env(name):
            say(f"  ok    {name} is set")
    if not todo:
        return
    if args.dry_run:
        for name, *_ in todo:
            say(f"  [dry-run] would ask for {name}")
        return
    if sys.platform != "win32":
        say("  Not Windows: add these to your shell profile instead (values from the team secret store):")
        for name, *_ in todo:
            say(f"    export {name}=...")
        return
    say("  Values come from the team secret store (ask the KB owner). Passwords aren't shown or printed.")
    for name, prompt, default, secret, _ in todo:
        set_user_env(name, ask(prompt, default, secret, get_user_env(name)))
        say(f"  set   {name}")


# ---------------------------------------------------------------- skills

def link(target: Path, link_path: Path, dry_run: bool) -> str:
    if link_path.exists() or link_path.is_symlink():
        resolved = Path(os.path.realpath(link_path))
        return "ok" if resolved == Path(os.path.realpath(target)) else "skip (exists, not a link to this repo)"
    if dry_run:
        return "[dry-run] link"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":     # a junction needs no admin rights
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link_path), str(target)], check=True, capture_output=True)
    else:
        link_path.symlink_to(target, target_is_directory=True)
    return "linked"


def setup_skills(args) -> None:
    say("\n[2/7] Skills")
    for tool in (".claude", ".cursor"):
        for skill in SKILLS:
            dest = Path.home() / tool / "skills" / skill
            say(f"  {link(ROOT / 'skills' / skill, dest, args.dry_run):<8} {dest}")


# ---------------------------------------------------------------- MCP

def cursor_server() -> dict:
    return {"command": "uvx", "args": list(MCP_ARGS),
            "env": {k: "${env:" + v + "}" for k, v in MCP_ENV.items()}}


def claude_add_args() -> list[str]:
    env = [x for k, v in MCP_ENV.items() for x in ("--env", f"{k}=${{{v}}}")]
    return ["mcp", "add", SERVER, "--scope", "user", *env, "--", "uvx", *MCP_ARGS]


def merge_cursor(cfg: dict) -> bool:
    """Add the KB server to a Cursor mcp.json dict. False if a server of that name is already there."""
    servers = cfg.setdefault("mcpServers", {})
    if SERVER in servers:
        return False
    servers[SERVER] = cursor_server()
    return True


def setup_mcp(args) -> None:
    say(f"\n[4/7] MCP server {SERVER} (read-only, your reader login)")
    if not shutil.which("uvx"):
        say("  WARN  uvx isn't on PATH: install uv (https://docs.astral.sh/uv/) so the server can start")
    path = Path.home() / ".cursor" / "mcp.json"
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not merge_cursor(cfg):
        say(f"  ok    Cursor: {SERVER} already in {path}")
    elif args.dry_run:
        say(f"  [dry-run] Cursor: add {SERVER} to {path}")
    else:
        if path.is_file():
            backup = path.with_name(f"mcp.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
            shutil.copy2(path, backup)
            say(f"  backup {backup}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        say(f"  added Cursor: {SERVER} in {path}")
    claude = shutil.which("claude")
    if not claude:
        say("  skip  Claude Code: 'claude' isn't on PATH")
        return
    listed = subprocess.run([claude, "mcp", "get", SERVER], capture_output=True, text=True)
    if listed.returncode == 0:
        say(f"  ok    Claude Code: {SERVER} already added")
    elif args.dry_run:
        say(f"  [dry-run] claude {' '.join(claude_add_args())}")
    else:
        done = subprocess.run([claude, *claude_add_args()], capture_output=True, text=True)
        say(f"  {'added' if done.returncode == 0 else 'FAILED'} Claude Code: {SERVER}"
            + ("" if done.returncode == 0 else f" ({done.stderr.strip()[:200]})"))


# ---------------------------------------------------------------- deps and check

KB_PY = ROOT / "skills" / "knowledge" / "scripts" / "kb.py"
UV_HINT = "install uv (https://docs.astral.sh/uv/; Windows: winget install astral-sh.uv, macOS: brew install uv)"


def uv_run(script: Path) -> list[str]:
    """How agents run a KB script: `uv run` reads its inline dependencies (# /// script) and uses a cached
    environment with them, so no pip install into the system Python is needed (Homebrew Python refuses it)."""
    return [shutil.which("uv") or "uv", "run", "--quiet", str(script)]


def setup_deps(args) -> None:
    say("\n[1/7] uv and kb.py's environment")
    if not shutil.which("uv"):
        say(f"  FAILED uv isn't on PATH: {UV_HINT}, then run setup again")
        return
    cmd = [*uv_run(KB_PY), "--help"]          # builds and caches kb.py's environment now, not in the first session
    if args.dry_run:
        say(f"  [dry-run] {' '.join(cmd)}")
        return
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    say("  ok" if done.returncode == 0 else f"  FAILED (exit {done.returncode}): {done.stderr.strip()[-300:]}")


# ---------------------------------------------------------------- Claude Code and Cursor instructions

CLAUDE_BEGIN = "<!-- BEGIN agent-capabilities (managed by setup-claude-code.ps1) -->"   # same block as that script
CLAUDE_END = "<!-- END agent-capabilities -->"


def claude_import() -> str:
    return "@" + (ROOT / "claude" / "CLAUDE.md").as_posix()


def ensure_claude_md(path: Path, dry_run: bool) -> str:
    """Make ~/.claude/CLAUDE.md import claude/CLAUDE.md (the working agreement and the KB rules). A managed block
    written by setup-claude-code.ps1 is left as it is; otherwise a minimal block is appended."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if claude_import() in text:
        return "ok"
    if CLAUDE_BEGIN in text:
        return "skip (a managed block without this checkout's import: run scripts/setup-claude-code.ps1)"
    if dry_run:
        return "[dry-run] add the import"
    block = f"{CLAUDE_BEGIN}\n{claude_import()}\n{CLAUDE_END}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text.rstrip() + "\n\n" if text.strip() else "") + block, encoding="utf-8")
    return "added"


def cursor_rules_block() -> str:
    """The User Rules text from cursor/user-rules.md (its ```text block)."""
    md = (ROOT / "cursor" / "user-rules.md").read_text(encoding="utf-8")
    return md.split("```text\n", 1)[1].split("\n```", 1)[0].strip() + "\n"


def rules_fingerprint() -> str:
    import hashlib
    return hashlib.sha256(cursor_rules_block().encode("utf-8")).hexdigest()[:16]


def copy_to_clipboard(text: str) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=text, text=True,
                           encoding="utf-8", check=True, capture_output=True)
        elif shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
        else:
            return False
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def setup_instructions(args, home: Path = Path.home()) -> None:
    say("\n[5/7] Claude Code: shared instructions and KB rules")
    say(f"  {ensure_claude_md(home / '.claude' / 'CLAUDE.md', args.dry_run):<8} {home / '.claude' / 'CLAUDE.md'}")
    say("\n[6/7] Cursor: KB rules (Cursor reads them only from Settings > Rules > User Rules)")
    marker = home / ".cursor" / "colossus-kb-user-rules.sha256"
    current = rules_fingerprint()
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == current:
        say("  ok    already pasted (this version of cursor/user-rules.md)")
        return
    if args.dry_run:
        say("  [dry-run] would copy the rules to the clipboard and ask you to paste them")
        return
    copied = copy_to_clipboard(cursor_rules_block())
    say(("  Copied to the clipboard." if copied else f"  Copy the block from {ROOT / 'cursor' / 'user-rules.md'}.")
        + " In Cursor: Settings > Rules > User Rules, paste it (replace an older copy), and close Settings.")
    if input("  Pasted? [y/N] ").strip().lower().startswith("y"):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(current + "\n", encoding="utf-8")
        say("  ok    noted; you won't be asked again unless the rules change")
    else:
        say("  not yet: the next run asks again")


# ---------------------------------------------------------------- verification

def saved_env() -> dict:
    """This process's environment with the KB settings as saved: what a newly started app sees."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("COLOSSUS_KB_")}
    env.update({n: v for n, *_ in SETTINGS if (v := get_user_env(n))})
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_check(cmd: list[str], env: dict) -> tuple[int, str]:
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return done.returncode, (done.stdout + done.stderr).strip()


def verify(reader_only: bool, home: Path = Path.home(), runner=run_check) -> list[tuple[str, bool, str]]:
    """Every part of the setup, checked with the saved settings. [(what, ok, detail)]; never prints a value."""
    results = []
    kb_py = uv_run(KB_PY)                     # exactly what agents and the SessionStart hook run
    env = saved_env()
    results.append(("uv installed", bool(shutil.which("uv")), "" if shutil.which("uv") else UV_HINT))
    needed = [n for n, _, _, _, ro in SETTINGS if ro or not reader_only]
    missing = [n for n in needed if not get_user_env(n)]
    results.append(("settings saved", not missing, ", ".join(missing) and f"missing {', '.join(missing)}"))
    retired = kb.retired_host(get_user_env("COLOSSUS_KB_URI"))
    results.append(("KB URI is the current instance", not retired,
                    f"saved URI is {retired}: run --reset and choose production" if retired else ""))
    for tool in (".claude", ".cursor"):
        link = home / tool / "skills" / "knowledge"
        results.append((f"skill linked for {tool[1:]}", Path(os.path.realpath(link)) == ROOT / "skills" / "knowledge",
                        str(link)))
    cursor_cfg = home / ".cursor" / "mcp.json"
    in_cursor = cursor_cfg.is_file() and SERVER in json.loads(cursor_cfg.read_text(encoding="utf-8")).get("mcpServers", {})
    results.append((f"{SERVER} in Cursor", in_cursor, str(cursor_cfg)))
    claude = shutil.which("claude")
    in_claude = bool(claude) and subprocess.run([claude, "mcp", "get", SERVER], capture_output=True).returncode == 0
    results.append((f"{SERVER} in Claude Code", in_claude, "" if claude else "'claude' isn't on PATH"))
    claude_md = home / ".claude" / "CLAUDE.md"
    results.append(("Claude Code imports the KB rules", claude_md.is_file() and
                    claude_import() in claude_md.read_text(encoding="utf-8"), str(claude_md)))
    marker = home / ".cursor" / "colossus-kb-user-rules.sha256"
    results.append(("Cursor User Rules pasted (as confirmed)", marker.is_file() and
                    marker.read_text(encoding="utf-8").strip() == rules_fingerprint(), "run setup again to paste"))
    code, out = runner([*kb_py, "status"], env)
    try:
        status = json.loads(out[out.index("{"):])
        detail = f"{status['connection'].split(' (')[0]}: {status['facts']} facts"
    except (ValueError, KeyError):
        status, detail = None, out[-200:]
    results.append(("KB reachable (kb.py status)", code == 0 and status is not None, detail))
    code, out = runner(uv_run(ROOT / "scripts" / "check_kb_readonly.py"), env)
    results.append(("read-only MCP reads, refuses writes", code == 0, out.splitlines()[-1] if out else ""))
    if not reader_only:
        code, out = runner([*kb_py, "write", "fact", "--id", "setup-check", "--category",
                            "technical/conventions/code-quality", "--kind", "rule", "--title", "Setup check",
                            "--summary", "Dry run only.", "--statement", "Dry run only.", "--why", "setup_kb.py check",
                            "--source-type", "conversation", "--source-ref", "setup_kb.py", "--via", "agent",
                            "--expected-current", "none", "--dry-run"], env)
        results.append(("writer login works (dry-run write, rolled back)", code == 0 and "DRY RUN" in out,
                        out.splitlines()[-1][:200] if out else ""))
    return results


def report(results: list[tuple[str, bool, str]]) -> int:
    for what, ok, detail in results:
        say(f"  {'ok  ' if ok else 'FAIL'}  {what}" + (f": {detail}" if detail and (not ok or what.startswith("KB reachable")) else ""))
    failed = [r for r in results if not r[1]]
    say(f"\n{'All checks passed.' if not failed else f'{len(failed)} check(s) failed: fix them and run --check again.'}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="setup_kb.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only verify the setup; change nothing")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen; change nothing")
    ap.add_argument("--reader-only", action="store_true", help="no writer login (look things up only)")
    ap.add_argument("--reset", action="store_true", help="ask again for settings that are already set")
    ap.add_argument("--no-deps", action="store_true", help="skip preparing kb.py's uv environment")
    ap.add_argument("--no-mcp", action="store_true", help="skip the MCP server")
    args = ap.parse_args(argv)
    say(f"agent-capabilities: {ROOT}")
    reader_only = args.reader_only or (args.check and not get_user_env("COLOSSUS_KB_PASSWORD"))
    if not args.check:
        if not args.no_deps:
            setup_deps(args)
        setup_skills(args)
        setup_env(args)
        if not args.no_mcp:
            setup_mcp(args)
        setup_instructions(args)
        if args.dry_run:
            return 0
    say("\n[7/7] Check (with the saved settings, as a restarted app sees them)")
    code = report(verify(reader_only))
    say("\nThen restart Cursor and Claude Code. In a new session: /mcp shows neo4j-colossus-kb connected, and")
    say('"use the knowledge skill: what is the rule for withdrawn runners?" answers from the KB, citing a fact id.')
    return code


if __name__ == "__main__":
    sys.exit(main())
