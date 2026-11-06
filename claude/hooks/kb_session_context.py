#!/usr/bin/env python3
"""Claude Code SessionStart hook: load the Colossus working agreement live from the KB graph (#19).

Prints `kb.py read context --path-prefix technical/workflow` to stdout, which Claude Code adds to the session. The graph
is the source of truth, so nothing is read from the markdown export. If the KB can't be reached (no login on this
machine, network), it prints one line saying so instead, and still exits 0 so the session starts normally. kb.py's
settings warnings (stale app settings, a staging or retired URI) are passed on, so a wrong instance is visible.

Installed into ~/.claude/settings.json by scripts/setup-claude-code.ps1.
"""
import shutil
import subprocess
import sys
from pathlib import Path

KB = Path(__file__).resolve().parents[2] / "skills" / "knowledge" / "scripts" / "kb.py"
PREFIX = "technical/workflow"
TIMEOUT_S = 8      # Aura answers in about 1 s, uv's cached environment adds little; offline, the driver would retry


def kb_command() -> list[str]:
    """Run kb.py as agents do: `uv run` brings its inline dependency (neo4j), which the plain Python may not have
    (e.g. Homebrew Python on macOS, #21). Without uv, fall back to this Python."""
    uv = shutil.which("uv")
    return [uv, "run", "--quiet", str(KB)] if uv else [sys.executable, str(KB)]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    try:
        run = subprocess.run([*kb_command(), "read", "context", "--path-prefix", PREFIX],
                             capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_S)
        warnings = [line for line in run.stderr.splitlines() if line.startswith("kb.py: WARNING")]
        if run.returncode in (0, 1) and run.stdout.strip():      # 1: connected, but no current facts under PREFIX
            print("\n\n".join([run.stdout.rstrip(), *warnings]))
            return 0
        reason = (run.stderr.strip().splitlines() or [f"kb.py exit {run.returncode}"])[-1]
    except subprocess.TimeoutExpired:
        reason = (f"kb.py timed out after {TIMEOUT_S}s; if a `git pull` just changed kb.py's dependency, uv may still "
                  "be preparing its environment: it loads next session, or run `python scripts/setup_kb.py --check`")
    except OSError as e:
        reason = str(e)
    print(f"Colossus KB working agreement not loaded ({reason}). For Colossus work, read it with the knowledge "
          f"skill: kb.py read context --path-prefix {PREFIX}. With no KB login, ask the user to run "
          f"`python scripts/setup_kb.py` in agent-capabilities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
