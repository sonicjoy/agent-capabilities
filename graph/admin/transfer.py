"""Dump and load the Colossus KB between instances (#15). Shared by dump.py and load.py; for humans only.

A dump is JSON lines: one header, then every KB node and relationship, keyed by business keys (never element ids):

    {"kind": "header", "format": 1, "source": "839b9d82…", "dumped_at": "…", "summary": {...}}
    {"kind": "node", "label": "KbFact", "extra_labels": [], "key": "f-1", "props": {...}}
    {"kind": "rel", "type": "KB_HAS_VERSION", "from": ["KbFact", "f-1"], "to": ["KbFactVersion", "v-1"], "props": {}}

Datetimes are written as {"$datetime": "<ISO 8601 with offset, nanoseconds>"}, plus "$zone": "<name>" when Neo4j stores
them with a named zone (Cypher's datetime() uses the named zone "UTC"; kb.py writes offsets). The zone kind comes from
Cypher, because the Python driver returns the same tzinfo for "Z" and for the named "UTC". Loading writes offsets as
offsets and named zones by name, so a re-dump is identical. KbMigration nodes are not
transferred: every instance records its own migrations (migrate.py). Only labels and types listed below are allowed,
so the load can't touch the instance's other graphs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter

import pytz                     # the neo4j driver's own dependency; its named zones are pytz zones
from neo4j.time import DateTime

FORMAT = 1
# Node label -> its unique business key (graph/migrations/001_constraints.cypher).
KEYS = {"KbLibrary": "name", "KbCategory": "path", "KbFact": "id", "KbFactVersion": "version_id",
        "KbPerson": "email", "KbSystemComponent": "name", "KbCodeRepo": "path"}
EXTRA_LABELS = {"KbFactVersion": {"KbCurrent"}}
NOT_TRANSFERRED = {"KbMigration"}
# Relationship type -> properties that tell two relationships of that type between the same nodes apart.
REL_IDENTITY = {"KB_RELATES_TO": ("rel",)}
REL_TYPES = {"KB_PART_OF", "KB_IN_CATEGORY", "KB_HAS_VERSION", "KB_SUPERSEDES", "KB_AUTHORED_BY", "KB_APPROVED_BY",
             "KB_RELATES_TO", "KB_DESCRIBES", "KB_IMPLEMENTED_IN"}


class TransferError(Exception):
    pass


# ---------------------------------------------------------------- values

# Cypher: {property: zone name} for the properties of `x` holding a datetime with a named zone. Lists of datetimes
# would lose it, so they are refused (the KB has none).
NAMED_ZONES = ("[k IN keys({x}) WHERE valueType({x}[k]) STARTS WITH 'ZONED DATETIME' "
               "AND NOT {x}[k].timezone =~ 'Z|[+-].*' | [k, {x}[k].timezone]]")
DATETIME_LISTS = "[k IN keys({x}) WHERE valueType({x}[k]) STARTS WITH 'LIST<ZONED DATETIME' | k]"


def encode(value, zone: str | None = None):
    if isinstance(value, DateTime):
        return {"$datetime": value.iso_format(), **({"$zone": zone} if zone else {})}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TransferError(f"can't dump a {type(value).__name__} property")


def decode(value):
    """Back to what Neo4j stored: a fixed offset (the driver sends it as an offset) or the named zone."""
    if isinstance(value, dict) and "$datetime" in value and set(value) <= {"$datetime", "$zone"}:
        parsed = DateTime.from_iso_format(value["$datetime"])
        if "$zone" in value:
            return parsed.astimezone(pytz.timezone(value["$zone"]))
        return parsed.replace(tzinfo=dt.timezone(parsed.utcoffset()))
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def _props(props: dict, zones: dict | None = None, lists=()) -> dict:
    if lists:
        raise TransferError(f"lists of datetimes ({list(lists)}) can't keep their zones; not supported")
    zones = zones or {}
    return {k: encode(v, zones.get(k)) for k, v in sorted(props.items())}


# ---------------------------------------------------------------- dump

def primary_label(labels: list[str]) -> str:
    primary = [l for l in labels if l in KEYS]
    unknown = [l for l in labels if l not in KEYS and l not in EXTRA_LABELS.get(primary[0] if primary else "", set())]
    if len(primary) != 1 or unknown:
        raise TransferError(f"can't transfer a node labelled {sorted(labels)}")
    return primary[0]


def dump_records(tx) -> list[dict]:
    """Every KB node and relationship (KbMigration excepted), in a stable order. Refuses anything it can't key."""
    records = []
    for label, key in sorted(KEYS.items()):
        for r in tx.run(f"MATCH (n:{label}) RETURN labels(n) AS labels, properties(n) AS props, "
                        f"{NAMED_ZONES.format(x='n')} AS zones, {DATETIME_LISTS.format(x='n')} AS lists "
                        f"ORDER BY n.{key}"):
            labels = r["labels"]
            primary_label(labels)                       # unknown extra labels stop the dump
            if r["props"].get(key) is None:
                raise TransferError(f"{label} without {key}")
            records.append({"kind": "node", "label": label, "key": r["props"][key],
                            "extra_labels": sorted(l for l in labels if l != label),
                            "props": _props(r["props"], dict(r["zones"]), r["lists"])})
    for r in tx.run("MATCH (a)-[r]->(b) WHERE type(r) STARTS WITH 'KB_' "
                    "RETURN type(r) AS type, labels(a) AS al, properties(a) AS ap, labels(b) AS bl, "
                    f"properties(b) AS bp, properties(r) AS props, {NAMED_ZONES.format(x='r')} AS zones, "
                    f"{DATETIME_LISTS.format(x='r')} AS lists"):
        if r["type"] not in REL_TYPES:
            raise TransferError(f"unknown relationship type {r['type']}")
        a, b = primary_label(r["al"]), primary_label(r["bl"])
        records.append({"kind": "rel", "type": r["type"], "from": [a, r["ap"][KEYS[a]]], "to": [b, r["bp"][KEYS[b]]],
                        "props": _props(r["props"], dict(r["zones"]), r["lists"])})
    nodes = [x for x in records if x["kind"] == "node"]
    rels = sorted((x for x in records if x["kind"] == "rel"), key=lambda x: json.dumps(x, sort_keys=True))
    return nodes + rels


def outside_counts(tx) -> dict:
    """Nodes per label and relationships per type that aren't the KB's: the load must leave these unchanged."""
    labels = {r["l"]: r["c"] for r in tx.run(
        "MATCH (n) WHERE NOT any(l IN labels(n) WHERE l STARTS WITH 'Kb') UNWIND labels(n) AS l "
        "RETURN l, count(*) AS c")}
    types = {r["t"]: r["c"] for r in tx.run(
        "MATCH ()-[r]->() WHERE NOT type(r) STARTS WITH 'KB_' RETURN type(r) AS t, count(*) AS c")}
    return {"labels": dict(sorted(labels.items())), "types": dict(sorted(types.items()))}


# ---------------------------------------------------------------- summary and comparison

def summary(records: list[dict]) -> dict:
    """Counts per label (with KbCurrent) and per type, the (id, version_id, statement) checksum of the plan, and a hash
    over every record."""
    labels, types = Counter(), Counter()
    fact_of = {}
    for x in records:
        if x["kind"] == "node":
            labels[x["label"]] += 1
            labels.update(x["extra_labels"])
        else:
            types[x["type"]] += 1
            if x["type"] == "KB_HAS_VERSION":
                fact_of[x["to"][1]] = x["from"][1]
    versions = sorted((fact_of.get(x["key"], ""), x["key"], x["props"].get("statement", ""))
                      for x in records if x["kind"] == "node" and x["label"] == "KbFactVersion")
    checksum = hashlib.sha256("\n".join("\x1f".join(v) for v in versions).encode("utf-8")).hexdigest()
    everything = hashlib.sha256("\n".join(json.dumps(x, sort_keys=True, ensure_ascii=False)
                                          for x in records).encode("utf-8")).hexdigest()
    return {"labels": dict(sorted(labels.items())), "types": dict(sorted(types.items())),
            "id_version_statement_sha256": checksum, "records_sha256": everything}


def differences(a: list[dict], b: list[dict], limit: int = 10) -> list[str]:
    """What differs between two dumps, by record identity (empty: identical)."""
    def ident(x):
        if x["kind"] == "node":
            return ("node", x["label"], x["key"])
        return ("rel", x["type"], tuple(x["from"]), tuple(x["to"]),
                tuple(x["props"].get(k) for k in REL_IDENTITY.get(x["type"], ())))
    ia, ib = {ident(x): x for x in a}, {ident(x): x for x in b}
    out = [f"only in the first: {k}" for k in sorted(set(ia) - set(ib), key=str)]
    out += [f"only in the second: {k}" for k in sorted(set(ib) - set(ia), key=str)]
    out += [f"differs: {k}" for k in sorted(set(ia) & set(ib), key=str) if ia[k] != ib[k]]
    return out[:limit] + ([f"... {len(out) - limit} more"] if len(out) > limit else [])


# ---------------------------------------------------------------- files

def write_dump(path, records: list[dict], source: str, dumped_at: str) -> dict:
    header = {"kind": "header", "format": FORMAT, "source": source, "dumped_at": dumped_at,
              "summary": summary(records)}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for x in [header, *records]:
            f.write(json.dumps(x, sort_keys=True, ensure_ascii=False) + "\n")
    return header


def read_dump(path) -> tuple[dict, list[dict]]:
    """(header, records). Refuses a file whose records don't match its header (truncated or edited)."""
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    if not lines or lines[0].get("kind") != "header" or lines[0].get("format") != FORMAT:
        raise TransferError(f"{path}: not a KB dump (format {FORMAT})")
    header, records = lines[0], lines[1:]
    if summary(records) != header["summary"]:
        raise TransferError(f"{path}: records don't match the header summary (truncated or edited?)")
    return header, records


# ---------------------------------------------------------------- load

def load_records(tx, records: list[dict]) -> dict:
    """MERGE every record by business key and set its properties exactly as dumped. Idempotent; touches only the
    allowed KB labels and types (label and type names come from the allowlists above, never from the file)."""
    for x in records:                                   # refuse the whole file before running anything
        if x["kind"] == "node" and x["label"] not in KEYS:
            raise TransferError(f"unknown node label {x['label']!r}")
        if x["kind"] == "rel" and x["type"] not in REL_TYPES:
            raise TransferError(f"unknown relationship type {x['type']!r}")
        if x["kind"] not in ("node", "rel"):
            raise TransferError(f"unknown record kind {x['kind']!r}")
    counts = Counter()
    for label, key in KEYS.items():
        rows = [{"key": x["key"], "props": {k: decode(v) for k, v in x["props"].items()},
                 "current": "KbCurrent" in x["extra_labels"]}
                for x in records if x["kind"] == "node" and x["label"] == label]
        for x in records:
            if x["kind"] == "node" and x["label"] == label:
                bad = set(x["extra_labels"]) - EXTRA_LABELS.get(label, set())
                if bad:
                    raise TransferError(f"{label} {x['key']}: unexpected labels {sorted(bad)}")
        if not rows:
            continue
        current = ("FOREACH (_ IN CASE WHEN row.current THEN [1] ELSE [] END | SET n:KbCurrent) "
                   "FOREACH (_ IN CASE WHEN row.current THEN [] ELSE [1] END | REMOVE n:KbCurrent) "
                   if label == "KbFactVersion" else "")
        tx.run(f"UNWIND $rows AS row MERGE (n:{label} {{{key}: row.key}}) SET n = row.props {current}",
               rows=rows).consume()
        counts[label] = len(rows)
    for rel_type in sorted(REL_TYPES):
        rels = [x for x in records if x["kind"] == "rel" and x["type"] == rel_type]
        for (a_label, b_label) in sorted({(x["from"][0], x["to"][0]) for x in rels}):
            if a_label not in KEYS or b_label not in KEYS:
                raise TransferError(f"{rel_type}: unknown endpoint labels {a_label}, {b_label}")
            rows = [{"a": x["from"][1], "b": x["to"][1], "props": {k: decode(v) for k, v in x["props"].items()}}
                    for x in rels if x["from"][0] == a_label and x["to"][0] == b_label]
            ident = ", ".join(f"{p}: row.props.{p}" for p in REL_IDENTITY.get(rel_type, ()))
            result = tx.run(
                f"UNWIND $rows AS row MATCH (a:{a_label} {{{KEYS[a_label]}: row.a}}) "
                f"MATCH (b:{b_label} {{{KEYS[b_label]}: row.b}}) "
                f"MERGE (a)-[r:{rel_type}{' {' + ident + '}' if ident else ''}]->(b) SET r = row.props "
                f"RETURN count(r) AS n", rows=rows).single()["n"]
            if result != len(rows):
                raise TransferError(f"{rel_type} {a_label}->{b_label}: {len(rows) - result} endpoints not found")
            counts[rel_type] += len(rows)
    return dict(counts)
