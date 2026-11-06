# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""Check that the read-only KB access can read but not write: `python scripts/check_kb_readonly.py`.

Run it after setup_kb.py, and on production after the migration (#15). The neo4j-colossus-kb MCP (as in
mcp/mcp.example.json) and the kb_reader login must both refuse writes.

Starts `uvx mcp-neo4j-cypher@0.6.0 --transport stdio --read-only` with the kb_reader login from the user's
COLOSSUS_KB_* variables (never printed), speaks MCP JSON-RPC over stdio, and tries to write:
  1. tools/list: is there a write tool at all?
  2. tools/call write_neo4j_cypher: refused?
  3. tools/call read_neo4j_cypher with a CREATE: refused?
  4. the database itself: a write with the kb_reader login in a transaction (rolled back either way).
Then confirms nothing was written.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "knowledge" / "scripts"))
import kb  # noqa: E402

PROBE = "CREATE (:KbFact {id: 'mcp-readonly-probe', created_at: datetime()}) RETURN 1"
COUNT = "MATCH (f:KbFact {id: 'mcp-readonly-probe'}) RETURN count(f) AS n"

conn = kb.reader_connection()
if conn.user != (kb.env("COLOSSUS_KB_READER_USER") or ""):
    sys.exit("COLOSSUS_KB_READER_USER/_PASSWORD aren't set; this check must use kb_reader, not the writer")
print(f"login: {conn.describe()}")

env = {**os.environ, "NEO4J_URI": conn.uri, "NEO4J_USERNAME": conn.user,
       "NEO4J_PASSWORD": conn.password, "NEO4J_DATABASE": conn.database}
args = json.loads((ROOT / "mcp" / "mcp.example.json").read_text(encoding="utf-8"))["mcpServers"]["neo4j-colossus-kb"]["args"]
print(f"server: uvx {' '.join(args)}")
proc = subprocess.Popen(["uvx", *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        env=env, text=True, encoding="utf-8")
ids = iter(range(1, 100))
failures = []


def rpc(method, params=None, notify=False):
    msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
    if not notify:
        msg["id"] = next(ids)
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            sys.exit("server closed the connection")
        reply = json.loads(line)
        if reply.get("id") == msg["id"]:
            return reply


def outcome(reply):
    if "error" in reply:
        return f"JSON-RPC error: {reply['error'].get('message')}"
    res = reply["result"]
    text = " ".join(c.get("text", "") for c in res.get("content", []))[:300]
    return f"{'isError ' if res.get('isError') else ''}{text}"


try:
    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "kb-readonly-check", "version": "1"}})
    rpc("notifications/initialized", notify=True)
    tools = [t["name"] for t in rpc("tools/list", {})["result"]["tools"]]
    print(f"1. tools offered: {tools}")
    if any("write" in t for t in tools):
        failures.append("the server offers a write tool")
    for step, tool in (("2.", "write_neo4j_cypher"), ("3.", "read_neo4j_cypher")):
        result = outcome(rpc("tools/call", {"name": tool, "arguments": {"query": PROBE}}))
        print(f"{step} {tool} CREATE -> {result}")
        if not (result.startswith("isError") or result.startswith("JSON-RPC error")):
            failures.append(f"{tool} accepted a CREATE")
    print(f"   read_neo4j_cypher count   -> {outcome(rpc('tools/call', {'name': 'read_neo4j_cypher', 'arguments': {'query': 'MATCH (f:KbFact) RETURN count(f) AS facts'}}))}")
finally:
    proc.terminate()

with kb.driver(conn) as drv, drv.session(database=conn.database) as s:
    tx = s.begin_transaction()
    try:
        tx.run(PROBE).consume()
        print("4. database, kb_reader write: ACCEPTED (unexpected)")
        failures.append("the database accepted a kb_reader write")
    except Exception as e:
        print(f"4. database, kb_reader write: refused: {getattr(e, 'code', type(e).__name__)}")
    finally:
        if not tx.closed():
            tx.rollback()
    left = s.run(COUNT).single()["n"]
    print(f"after: probe nodes in the KB = {left}")
if left:
    failures.append(f"{left} probe node(s) were written")
print("OK: read-only" if not failures else "FAILED: " + "; ".join(failures))
sys.exit(1 if failures else 0)
