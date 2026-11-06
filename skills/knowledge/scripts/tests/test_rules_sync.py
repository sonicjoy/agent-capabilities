"""cursor/user-rules.md is the always-on rules for Cursor, which doesn't load rule files from ~/.cursor/rules. The rule
files in rules/ are the source: every always-on rule must be covered by the block (or deliberately left out), and the
block must keep each rule's key points, so the two can't drift apart silently."""
import re

import pytest

from conftest import ROOT

BLOCK = (ROOT / "cursor" / "user-rules.md").read_text(encoding="utf-8")
# The key points each rule and the Cursor block must both state (case-insensitive substrings).
KEY_POINTS = {
    "kb-lookup-triggers": ["knowledge", "kb.py", "before proposing a fix", "pools", "settlement", "commingling",
                           "statsfeed", "typos", "fact ids", "only source of truth", "setup_kb.py"],
    "kb-writes-via-skill-only": ["kb.py write", "--dry-run", "neo4j mcp", "graph/admin", "knowledge/colossus-bets/",
                                 "kb.py export", "offer an export mr"],
    "gitlab-work-item-sync": ["one", "work item", "plan — start", "plan — progress", "plan — done", "same turn",
                              "someone else's issue"],
}
# Always-on rules that are not about Colossus knowledge or process, so they stay out of the Cursor block.
NOT_IN_BLOCK = {"run-probe-scripts", "bandit-quality-gate"}


def plain(text: str) -> str:
    """Lower-cased, without markdown emphasis, so **before** proposing a fix matches."""
    return text.replace("**", "").replace("`", "").lower()


def always_on_rules():
    return sorted(p.stem for p in (ROOT / "rules").glob("*.mdc")
                  if re.search(r"(?m)^alwaysApply:\s*true", p.read_text(encoding="utf-8")))


def test_every_always_on_rule_is_in_the_cursor_block_or_excluded():
    assert set(always_on_rules()) == set(KEY_POINTS) | NOT_IN_BLOCK


@pytest.mark.parametrize("rule", sorted(KEY_POINTS))
def test_rule_and_cursor_block_state_the_same_key_points(rule):
    text = plain((ROOT / "rules" / f"{rule}.mdc").read_text(encoding="utf-8"))
    block = plain(BLOCK)
    assert [k for k in KEY_POINTS[rule] if k not in text] == [], f"rules/{rule}.mdc lost a key point"
    assert [k for k in KEY_POINTS[rule] if k not in block] == [], f"cursor/user-rules.md lost a key point of {rule}"


def test_claude_md_loads_every_always_on_rule():
    """Imported with @, or (for a glob-scoped rule like bandit-quality-gate) pointed to by path."""
    claude_md = (ROOT / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert [r for r in always_on_rules() if f"rules/{r}.mdc" not in claude_md] == []
