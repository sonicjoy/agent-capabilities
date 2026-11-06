"""Write commands for kb.py: facts, retractions, draft promotion, links, components, repos, categories.

Every function takes an open transaction and runs only templates from graph/queries/write/. Each one ends by running
all integrity checks in the same transaction, so a write that would leave the KB inconsistent raises KbError and the
caller rolls back. Nothing is deleted except a fact's KB_IN_CATEGORY link when it moves category.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from kb import KbError, check_problems, integrity_checks, load_template

KINDS = ("rule", "decision", "description", "procedure", "glossary", "lesson")
VIAS = ("human", "agent")
CONFIDENCES = ("verified", "inferred")
RELS = ("depends_on", "see_also", "contradicts", "example_of")
CHANGE_TYPES = ("change", "correction")
# Categories whose writes are always drafts and need a different person to promote them. Add settlement here later.
HIGH_RISK_PREFIXES = ("business/pools",)
KEYWORD_RESERVED = (":", "/", "*")
FACT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORY_PATH = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:/[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)*$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EVIDENCE_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+(/\S*)?$")
CONTENT = ("title", "summary", "statement", "keywords", "kind")
CONTEXT = ("why", "context", "alternatives", "trade_offs", "revisit_if")
# Things that look like credentials. Everything with the reader login can read the KB, so writes refuse them
# (ingest, #7, uses the same scan). Values written as placeholders (<...>, {...}, $VAR) don't match.
SECRET_PATTERNS = (
    ("a private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("an AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("a GitLab token", r"\bglpat-[0-9A-Za-z_-]{20,}"),
    ("a GitHub token", r"\bgh[pousr]_[0-9A-Za-z]{30,}"),
    ("a Slack token", r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    ("a JWT", r"\beyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}"),
    ("credentials in a URL", r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@"),
    ("a password, secret, token or key assignment",
     r"(?i)\b(?:pass(?:word|wd)?|secret|api[_-]?key|token|access[_-]?key)\b\s*[:=]\s*['\"]?(?![<{$])[^\s'\"]{6,}"),
)


def find_secrets(fields: dict) -> list[tuple[str, str]]:
    """(field, what) for every field whose text looks like it contains a credential. Never returns the value."""
    hits = []
    for name, value in fields.items():
        texts = value if isinstance(value, list) else [value]
        for text in texts:
            if not text:
                continue
            for what, pattern in SECRET_PATTERNS:
                if re.search(pattern, text):
                    hits.append((name, what))
    return hits


def _refuse_secrets(fields: dict) -> None:
    hits = find_secrets(fields)
    _require(not hits, "write refused: " + "; ".join(f"--{n.replace('_', '-')} looks like it contains {w}" for n, w in hits)
             + ". Remove it: everyone with the reader login can read the KB")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_high_risk(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in HIGH_RISK_PREFIXES)


def _native(value):
    """neo4j temporal values -> Python datetimes in offset UTC (datetime.timezone.utc), recursively.

    Neo4j hands back DateTimes with a *named* zone ('UTC'). Written back as-is they don't compare equal in Cypher to
    the same instant stored with an offset (+00:00), which breaks find_predecessor and never-valid retractions.
    Everything kb.py writes therefore uses offset UTC."""
    if hasattr(value, "to_native"):
        native = value.to_native()
        return native.astimezone(timezone.utc) if isinstance(native, datetime) and native.tzinfo else native
    if isinstance(value, dict):
        return {k: _native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_native(v) for v in value]
    return value


def run(tx, root, template: str, **params) -> list[dict]:
    return [_native(r.data()) for r in tx.run(load_template(root, "write", template), **params)]


def guard_integrity(tx, root) -> None:
    """Refuse the write (the caller rolls back) if the KB would be inconsistent after it."""
    problems = check_problems(tx, integrity_checks(root))
    if problems:
        listed = "; ".join(f"{p['check']}: {p['detail']}" for p in problems[:5])
        raise KbError(f"write refused, the KB would fail integrity ({len(problems)} problem(s)): {listed}")


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise KbError(message)


def _check_person(email: str, role: str) -> str:
    _require(bool(email) and bool(EMAIL.match(email)), f"--{role} must be an email address")
    return email.lower()


def _leaf_category(tx, root, path: str) -> dict:
    rows = run(tx, root, "category_info", path=path)
    _require(bool(rows), f"no category {path!r}; create it with: kb.py write category")
    _require(not rows[0]["has_children"], f"category {path!r} has sub-categories; facts go in leaf categories only")
    return rows[0]


@dataclass
class FactInput:
    id: str
    why: str
    source_type: str
    source_refs: list[str]
    author: str
    via: str
    category: str | None = None
    kind: str | None = None
    title: str | None = None
    summary: str | None = None
    statement: str | None = None
    keywords: list[str] | None = None
    context: str | None = None
    alternatives: str | None = None
    trade_offs: str | None = None
    revisit_if: str | None = None
    confidence: str = "verified"
    change_type: str | None = None          # None = create for a new fact, change for an existing one
    valid_from: datetime | None = None
    expected_current: str | None = None
    draft: bool = False
    author_name: str | None = None
    extra: dict = field(default_factory=dict)


# Only the one-off legacy ingest (ingest/markdown_to_graph.py) may use these; kb.py write can't reach them.
INGEST_VIA, INGEST_CONFIDENCE, INGEST_EXTRA = "ingest", "legacy_ingest", ("legacy_updated",)


def _validate_common(inp: FactInput, ingest: bool = False) -> None:
    _require(bool(FACT_ID.match(inp.id or "")), "--id must be a lower-case kebab slug, e.g. pool-restart-event-ordering")
    _require(bool(inp.why and inp.why.strip()), "--why is required: say why this version exists")
    _require(bool(inp.source_type and inp.source_type.strip()), "--source-type is required")
    _require(bool(inp.source_refs) and all(r.strip() for r in inp.source_refs), "at least one non-blank --source-ref")
    _require(inp.via in VIAS or (ingest and inp.via == INGEST_VIA), f"--via must be one of {VIAS}")
    _require(inp.confidence in CONFIDENCES or (ingest and inp.confidence == INGEST_CONFIDENCE),
             f"--confidence must be one of {CONFIDENCES}")
    _require(not inp.extra or (ingest and set(inp.extra) <= set(INGEST_EXTRA)), "unexpected extra properties")
    _require(inp.change_type in (None,) + CHANGE_TYPES, f"--change-type must be one of {CHANGE_TYPES}")
    if inp.kind is not None:
        _require(inp.kind in KINDS, f"--kind must be one of {KINDS}")
    if inp.keywords is not None:
        _require(all(k.strip() for k in inp.keywords), "keywords can't be blank")
        # The export's Quick Reference ("- kw1 / kw2: file.md - summary") must read back as the same keywords.
        _require(not any(c in k for k in inp.keywords for c in KEYWORD_RESERVED),
                 f"keywords can't contain {' '.join(KEYWORD_RESERVED)} (they'd break the exported Quick Reference)")
    for name in ("title", "summary", "statement"):
        value = getattr(inp, name)
        _require(value is None or bool(value.strip()), f"--{name} can't be blank")


def _supersede(tx, root, fact_id: str, new_vid: str, old: dict, change_type: str, new_valid_from, now) -> dict:
    """Close `old` for the new version and, for a correction that moves valid_from, move the predecessor's valid_to."""
    moved = None
    if old["status"] == "retracted":           # re-activating a retracted fact: the retraction stays as it was
        status, valid_to, recorded_to = "retracted", old["valid_to"], old["recorded_to"]
    elif change_type == "change":
        status, valid_to, recorded_to = "superseded", new_valid_from, now
    else:                                       # correction: the old text was wrong; its business dates aren't closed
        status, valid_to, recorded_to = "superseded", old["valid_to"], now
    if change_type == "correction" and new_valid_from != old["valid_from"]:
        preds = run(tx, root, "find_predecessor", id=fact_id, old=old["version_id"], old_valid_from=old["valid_from"])
        for pred in preds:
            _require(new_valid_from > pred["valid_from"],
                     f"--valid-from must be after the previous rule's start ({pred['valid_from']}), "
                     f"version {pred['version_id']}")
            run(tx, root, "set_valid_to", vid=pred["version_id"], valid_to=new_valid_from)
            moved = pred["version_id"]
    run(tx, root, "supersede", new=new_vid, old=old["version_id"], old_status=status, old_valid_to=valid_to,
        old_recorded_to=recorded_to)
    return {"superseded": old["version_id"], "predecessor_valid_to_moved": moved}


def write_fact(tx, root, inp: FactInput, now: datetime | None = None, ingest: bool = False,
               ingest_active: bool = False) -> dict:
    """Create a fact, or write a new version of it (change or correction), as active or draft.
    `ingest` / `ingest_active` are for the legacy ingest only: they allow via=ingest, confidence=legacy_ingest and
    legacy_updated, and (ingest_active) load high-risk categories as active instead of drafts."""
    now = now or utcnow()
    _validate_common(inp, ingest)
    author = _check_person(inp.author, "author")
    if inp.valid_from is not None:
        _require(inp.valid_from <= now, "--valid-from can't be in the future (future-dated rules aren't supported)")
    state = run(tx, root, "lock_fact", id=inp.id)
    state = state[0] if state else None
    cur = state["current"] if state else None
    base = cur or (state["open_retraction"] if state else None)

    # Concurrency: the caller states which version it is replacing; refuse if someone else got there first.
    if state is None:
        _require(inp.expected_current is None, f"fact {inp.id!r} doesn't exist yet; drop --expected-current")
    else:
        expected = base["version_id"] if base else None
        _require(inp.expected_current == expected,
                 f"fact {inp.id!r} changed: its latest version is {expected!r}, not {inp.expected_current!r}. "
                 f"Re-read it (kb.py read fact --id {inp.id}) and retry with --expected-current {expected}")

    change_type = inp.change_type or ("change" if base else "create")
    if not base:
        _require(change_type == "create", f"fact {inp.id!r} has no version to {change_type}; leave --change-type out")
    if change_type == "correction":
        _require(cur is not None, "a correction needs a current version; re-activate a retracted fact with a change")

    # Omitted fields keep the latest version's value: the current one, or the retracted one being brought back.
    content = {k: getattr(inp, k) if getattr(inp, k) is not None else (base or {}).get(k) for k in CONTENT}
    missing = [k for k in ("title", "summary", "statement", "kind") if not content[k]]
    _require(not missing, f"missing --{', --'.join(missing)}"
             + (" for a new fact" if state is None else f" (fact {inp.id!r} has no version to copy them from)"))
    _refuse_secrets({**{k: content[k] for k in CONTENT}, **{k: getattr(inp, k) for k in CONTEXT},
                     "source_ref": inp.source_refs})
    category = inp.category or (state["category"] if state else None)
    _require(bool(category) and bool(CATEGORY_PATH.match(category)), "--category is required for a new fact")
    moved_category = state is not None and category != state["category"]
    if state is None or moved_category:
        _leaf_category(tx, root, category)

    if change_type == "correction":
        valid_from = inp.valid_from or cur["valid_from"]
        valid_to = cur["valid_to"]
    else:
        valid_from = inp.valid_from or now
        valid_to = None
        if change_type == "change" and cur:
            _require(valid_from > cur["valid_from"], f"--valid-from must be after the current version's start "
                                                     f"({cur['valid_from']}); use --change-type correction to fix it")
        if change_type == "change" and not cur and base:     # after a retraction
            _require(valid_from >= base["valid_to"], f"--valid-from must be on or after the retraction ({base['valid_to']})")

    if cur and change_type == "change" and not moved_category and inp.valid_from is None:
        _require(any(content[k] != cur.get(k) for k in CONTENT), "nothing changed: same content as the current version")

    draft = inp.draft or (is_high_risk(category) and not (ingest and ingest_active))
    if state is None:
        run(tx, root, "create_fact", id=inp.id, category=category, now=now)
    vid = str(uuid.uuid4())
    props = {**content, "status": "draft" if draft else "active", "change_type": change_type,
             "valid_from": valid_from, "valid_to": valid_to, "recorded_at": now,
             "source_type": inp.source_type.strip(), "source_refs": [r.strip() for r in inp.source_refs],
             "confidence": inp.confidence, "via": inp.via,
             # a draft remembers what it was written against; promote refuses if the fact has moved on since
             "base_version_id": base["version_id"] if (draft and base) else None,
             **{k: getattr(inp, k) for k in CONTEXT}, **(inp.extra if ingest else {})}
    run(tx, root, "create_version", id=inp.id, vid=vid, props=props, current=not draft,
        author=author, author_name=inp.author_name)
    result = {"id": inp.id, "version_id": vid, "status": props["status"], "change_type": change_type,
              "category": category, "valid_from": valid_from}
    if draft:
        result["note"] = (f"saved as a draft ({category} needs approval)" if is_high_risk(category) else "saved as a draft") \
            + f"; promote with: kb.py write promote --version-id {vid} --expected-current {base['version_id'] if base else 'none'}" \
            + " (run by someone else, or by you with --confirmed-by EMAIL --evidence URL)"
    else:
        if base:
            result.update(_supersede(tx, root, inp.id, vid, base, change_type, valid_from, now))
        if moved_category:
            run(tx, root, "move_category", id=inp.id, category=category)
            result["moved_from"] = state["category"]
    guard_integrity(tx, root)
    return result


def retract(tx, root, fact_id: str, why: str, source_refs: list[str], author: str, expected_current: str | None,
            never_valid: bool = False, now: datetime | None = None) -> dict:
    """Retract the current version: the rule no longer applies (or, with never_valid, never did)."""
    now = now or utcnow()
    _require(bool(why and why.strip()), "--why is required")
    _require(bool(source_refs) and all(r.strip() for r in source_refs), "at least one non-blank --source-ref")
    author = _check_person(author, "author")
    state = run(tx, root, "lock_fact", id=fact_id)
    _require(bool(state), f"no fact {fact_id!r}")
    cur = state[0]["current"]
    _require(cur is not None, f"fact {fact_id!r} has no current version to retract")
    _require(expected_current == cur["version_id"],
             f"fact {fact_id!r} changed: current is {cur['version_id']!r}, not {expected_current!r}")
    _refuse_secrets({"why": why, "source_ref": source_refs})
    if never_valid:
        preds = run(tx, root, "find_predecessor", id=fact_id, old=cur["version_id"], old_valid_from=cur["valid_from"])
        _require(not preds, f"--never-valid would leave a gap: {cur['version_id']} replaced {preds[0]['version_id'] if preds else ''}, "
                            "which would then end on a date nothing follows. To undo a wrong change, write a correction "
                            "(--change-type correction) with the right content instead")
    valid_to = cur["valid_from"] if never_valid else now
    run(tx, root, "retract", vid=cur["version_id"], now=now, valid_to=valid_to, why=why.strip(),
        source_refs=[r.strip() for r in source_refs], author=author)
    guard_integrity(tx, root)
    return {"id": fact_id, "version_id": cur["version_id"], "status": "retracted", "never_valid": never_valid}


def promote(tx, root, version_id: str, approver: str, expected_current: str | None, approver_name: str | None = None,
            now: datetime | None = None, confirmed_by: str | None = None, evidence: str | None = None,
            confirmed_by_name: str | None = None) -> dict:
    """Make a draft active and current. Someone other than the author approves it: the person running the promote,
    or, when that is the author, the person named in `confirmed_by`, with `evidence` linking to their confirmation.
    `confirmed_by` must already be in the KB unless `confirmed_by_name` is given, so a typo can't become an approver."""
    now = now or utcnow()
    approver = _check_person(approver, "approver")
    info = run(tx, root, "draft_info", vid=version_id)
    _require(bool(info), f"no version {version_id!r}")
    d = info[0]
    _require(d["status"] == "draft", f"version {version_id!r} is {d['status']}, not a draft")
    author = (d["author"] or "").lower()
    recorded_by = None
    if approver == author:
        _require(confirmed_by is not None and evidence is not None,
                 "you wrote this draft: name who confirmed it with --confirmed-by EMAIL and link their confirmation "
                 "with --evidence URL (e.g. a work-item comment)")
        _require(approver_name is None, "--approver-name doesn't go with --confirmed-by; use --confirmed-by-name")
        confirmed_by = _check_person(confirmed_by, "confirmed-by")
        _require(confirmed_by != author, "--confirmed-by must be a different person from the author")
        evidence = evidence.strip()
        _require(bool(EVIDENCE_URL.match(evidence)), "--evidence must be an http(s) link to the confirmation")
        _refuse_secrets({"evidence": evidence})
        if not run(tx, root, "person_info", email=confirmed_by):
            _require(bool((confirmed_by_name or "").strip()),
                     f"{confirmed_by} isn't in the KB yet: check the address, and if it's right, add their name "
                     f"with --confirmed-by-name")
        approver, approver_name, recorded_by = confirmed_by, (confirmed_by_name or "").strip() or None, approver
    else:
        _require(confirmed_by is None and evidence is None and confirmed_by_name is None,
                 "--confirmed-by, --confirmed-by-name and --evidence are only for the draft's author; "
                 "you approve it yourself by running promote")
    state = run(tx, root, "lock_fact", id=d["id"])[0]
    cur = state["current"]
    base = cur or state["open_retraction"]
    expected = base["version_id"] if base else None
    _require(expected_current == expected,
             f"fact {d['id']!r} changed since the draft: latest version is {expected!r}, not {expected_current!r}")
    _require(d["base_version_id"] == expected,
             f"draft {version_id} was written against {d['base_version_id'] or 'no version'}, but the fact's latest "
             f"version is now {expected}. Promoting it would overwrite that change: write a new draft from the "
             f"current version instead")
    change_type = d["change_type"]
    if change_type == "create":
        _require(base is None, f"fact {d['id']!r} already has versions; this draft can't create it")
    elif change_type == "correction":
        _require(cur is not None, "a correction needs a current version")
    elif cur:
        _require(d["valid_from"] > cur["valid_from"], "the draft's valid_from is no longer after the current version's")
    run(tx, root, "promote", vid=version_id, now=now, approver=approver, approver_name=approver_name,
        recorded_by=recorded_by, evidence=evidence)
    result = {"id": d["id"], "version_id": version_id, "status": "active", "change_type": change_type,
              "approved_by": approver}
    if recorded_by:
        result.update(approval_recorded_by=recorded_by, approval_evidence=evidence)
    if base:
        result.update(_supersede(tx, root, d["id"], version_id, base, change_type, d["valid_from"], now))
    guard_integrity(tx, root)
    return result


def link(tx, root, link_type: str, source: str, target: str, rel: str | None = None) -> dict:
    """relates_to (fact -> fact, with --rel), describes (fact -> component), implemented_in (fact/component -> repo)."""
    if link_type == "relates_to":
        _require(rel in RELS, f"--rel must be one of {RELS}")
        _require(source != target, "a fact can't relate to itself")
        rows = run(tx, root, "link_relates_to", **{"from": source, "to": target, "rel": rel})
    elif link_type == "describes":
        rows = run(tx, root, "link_describes", **{"from": source, "to": target})
    elif link_type == "implemented_in":
        kind = _source_kind(tx, root, source)
        rows = run(tx, root, "link_implemented_in", **{"from": source, "from_kind": kind, "to": target})
    else:
        raise KbError("--type must be relates_to, describes or implemented_in")
    _require(bool(rows) and rows[0]["linked"] > 0, f"nothing linked: check that {source!r} and {target!r} exist")
    guard_integrity(tx, root)
    return {"type": link_type, "from": source, "to": target, "rel": rel}


def _source_kind(tx, root, source: str) -> str:
    kinds = run(tx, root, "source_kinds", **{"from": source})[0]
    _require(not (kinds["fact"] and kinds["component"]),
             f"{source!r} is both a fact id and a component name; rename one of them")
    return "fact" if kinds["fact"] else "component"


def unlink(tx, root, link_type: str, source: str, target: str, rel: str | None = None) -> dict:
    """Remove a mistaken link (links aren't versioned). Facts, versions and categories are never deleted."""
    if link_type == "relates_to":
        _require(rel in RELS, f"--rel must be one of {RELS}")
        rows = run(tx, root, "unlink_relates_to", **{"from": source, "to": target, "rel": rel})
    elif link_type == "describes":
        rows = run(tx, root, "unlink_describes", **{"from": source, "to": target})
    elif link_type == "implemented_in":
        rows = run(tx, root, "unlink_implemented_in",
                   **{"from": source, "from_kind": _source_kind(tx, root, source), "to": target})
    else:
        raise KbError("--type must be relates_to, describes or implemented_in")
    _require(rows[0]["unlinked"] > 0, f"no {link_type} link from {source!r} to {target!r}")
    guard_integrity(tx, root)
    return {"type": link_type, "from": source, "to": target, "rel": rel, "removed": rows[0]["unlinked"]}


def upsert_component(tx, root, name: str, kind: str | None, description: str | None) -> dict:
    _require(bool(name and name.strip()), "--name is required")
    run(tx, root, "upsert_component", name=name.strip(), kind=kind, description=description)
    guard_integrity(tx, root)
    return {"component": name.strip()}


def upsert_repo(tx, root, path: str, web_url: str | None) -> dict:
    _require(bool(re.match(r"^[\w.-]+(/[\w.-]+)+$", path or "")), "--path must look like group/project")
    run(tx, root, "upsert_repo", path=path, web_url=web_url)
    guard_integrity(tx, root)
    return {"repo": path}


def create_category(tx, root, path: str, title: str, description: str | None) -> dict:
    """A new category. Its parent must exist and hold no facts, because facts live in leaf categories only."""
    _require(bool(CATEGORY_PATH.match(path or "")) and "/" in path, "--path must be like business/glossary")
    _require(bool(title and title.strip()), "--title is required")
    _require(not run(tx, root, "category_info", path=path), f"category {path!r} already exists")
    parent = run(tx, root, "category_info", path=path.rsplit("/", 1)[0])
    _require(bool(parent), f"parent category {path.rsplit('/', 1)[0]!r} doesn't exist")
    _require(parent[0]["facts"] == 0, f"parent {parent[0]['path']!r} holds facts; move them to leaf categories first")
    run(tx, root, "create_category", path=path, title=title.strip(), description=description)
    guard_integrity(tx, root)
    return {"category": path}
