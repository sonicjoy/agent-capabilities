#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["neo4j==6.4.0"]
# ///
"""Manage the KB logins on an instance, as its admin. For humans; agents don't run graph/admin/*.

    python graph/admin/kb_users.py add alberto manuel   per person: kb_<name> (publisher) and kb_<name>_reader (reader)
    python graph/admin/kb_users.py remove alberto       drop that person's two logins (their knowledge stays)
    python graph/admin/kb_users.py set-password alberto new passwords for both of alberto's logins
    python graph/admin/kb_users.py set-password kb_alberto_reader   ... or for one login
    python graph/admin/kb_users.py create               the shared kb_reader (reader) and kb_writer (publisher)
    python graph/admin/kb_users.py remove-shared --yes  production: drop the shared logins once everyone has their own
    python graph/admin/kb_users.py suspend-writer       freeze KB writes: suspend every kb_ login with publisher
    python graph/admin/kb_users.py activate-writer      undo the freeze
    python graph/admin/kb_users.py show                 the kb_ users, their roles and status

Target: COLOSSUS_KB_URI. Admin login: COLOSSUS_KB_ADMIN_USER / _PASSWORD from this terminal session only, as for
migrate.py. Aura Query runs as the console account, which may not manage users; this script uses the admin login.
New passwords are typed at a prompt that shows * per character, never passed on the command line or printed. Use new
passwords per instance and hand them over through the team secret store. `add` skips logins that already exist and
keeps their password. A person who leaves is removed, not suspended: suspension is reserved for the freeze, so
activate-writer can reactivate every suspended writer login.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(os.path.realpath(__file__)).parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "knowledge" / "scripts"))
sys.path.insert(0, str(HERE))
import kb  # noqa: E402
import migrate  # noqa: E402
from neo4j.exceptions import AuthError, Forbidden  # noqa: E402

SHOW = "SHOW USERS WHERE user STARTS WITH 'kb_'"
NAME = re.compile(r"[a-z][a-z0-9]{1,30}")
RESERVED = {"reader", "writer"}            # kb_reader / kb_writer are the shared logins
SHARED = ("kb_reader", "kb_writer")


def new_password(who: str) -> str:
    first = kb.read_secret(f"new password for {who} (shown as *): ")
    if len(first) < 12 or first != kb.read_secret(f"again for {who}: "):
        raise kb.KbError(f"passwords for {who} didn't match or are shorter than 12 characters")
    return first


def person_logins(name: str) -> list[tuple[str, str]]:
    """(login, role) for one person, e.g. alberto -> kb_alberto (publisher), kb_alberto_reader (reader)."""
    name = name.strip().lower()
    if not NAME.fullmatch(name) or name in RESERVED:
        raise kb.KbError(f"{name!r}: use a first name, lower-case letters and digits only (not reader/writer)")
    return [(f"kb_{name}", "publisher"), (f"kb_{name}_reader", "reader")]


def users(session) -> list[dict]:
    return sorted((r.data() for r in session.run(SHOW)), key=lambda r: r["user"])


def create(session, logins: list[tuple[str, str]], existing: set[str]) -> None:
    """Create the logins that don't exist yet (asking for each password first), then grant every login its role.
    The grant runs for existing logins too (it is idempotent), so re-running repairs a run that stopped between
    CREATE USER and GRANT ROLE."""
    todo = [(login, role) for login, role in logins if login not in existing]
    passwords = {login: new_password(login) for login, _ in todo}   # all prompts before any change
    for login, role in logins:
        if login in passwords:
            session.run(f"CREATE USER {login} IF NOT EXISTS SET PASSWORD $p CHANGE NOT REQUIRED",
                        p=passwords[login]).consume()
        session.run(f"GRANT ROLE {role} TO {login}").consume()
        print(f"  {'created' if login in passwords else 'exists, password kept:'} {login} ({role})")


def password_targets(arg: str) -> list[str]:
    """Logins whose password set-password changes: a first name means both of that person's logins; a login name
    (kb_alberto, kb_alberto_reader, or a shared kb_reader / kb_writer) means just that one."""
    if arg in SHARED:
        return [arg]
    login = re.fullmatch(r"kb_([a-z0-9]+?)(_reader)?", arg)
    if login:
        person_logins(login.group(1))           # validates the name
        return [arg]
    return [name for name, _ in person_logins(arg)]


def set_passwords(session, logins: list[str], existing: set[str]) -> None:
    """New passwords for existing logins: all prompts before any change; an unknown login changes nothing."""
    missing = [login for login in logins if login not in existing]
    if missing:
        raise kb.KbError(f"no such login: {', '.join(missing)} (add the person first)")
    passwords = {login: new_password(login) for login in dict.fromkeys(logins)}
    for login, password in passwords.items():
        session.run(f"ALTER USER {login} SET PASSWORD $p CHANGE NOT REQUIRED", p=password).consume()
        print(f"  new password set: {login}")


def roleless(rows: list[dict]) -> list[str]:
    """kb_ logins with neither reader nor publisher: a run that stopped half-way, or a mistake."""
    return [r["user"] for r in rows if not {"reader", "publisher"} & set(r.get("roles") or [])]


def writer_logins(rows: list[dict], suspended: bool) -> list[str]:
    return [r["user"] for r in rows if "publisher" in (r.get("roles") or []) and bool(r.get("suspended")) == suspended]


def run(command: str, session, names: list[str] | None = None) -> None:
    names = names or []
    if command in ("add", "remove", "set-password") and not names:
        raise kb.KbError(f"{command}: name at least one person, e.g. {command} alberto")
    if command == "create":
        create(session, [("kb_reader", "reader"), ("kb_writer", "publisher")], {r["user"] for r in users(session)})
    elif command == "add":
        create(session, [pair for n in names for pair in person_logins(n)], {r["user"] for r in users(session)})
    elif command == "set-password":
        set_passwords(session, [t for n in names for t in password_targets(n)], {r["user"] for r in users(session)})
    elif command == "remove":
        existing = {r["user"] for r in users(session)}
        for login, _ in [pair for n in names for pair in person_logins(n)]:
            if login in existing:
                session.run(f"DROP USER {login} IF EXISTS").consume()
                print(f"  removed {login}")
            else:
                print(f"  not found: {login}")
    elif command == "remove-shared":
        rows = users(session)
        people = [u for u in writer_logins(rows, suspended=False) if u != "kb_writer"]
        if not people:
            raise kb.KbError("no active per-person writer login (kb_<name>) yet: add people before removing the "
                             "shared logins")
        for login in SHARED:
            if login in {r["user"] for r in rows}:
                session.run(f"DROP USER {login} IF EXISTS").consume()
                print(f"  removed {login}")
    elif command in ("suspend-writer", "activate-writer"):
        suspend = command == "suspend-writer"
        for login in writer_logins(users(session), suspended=not suspend):
            session.run(f"ALTER USER {login} SET STATUS {'SUSPENDED' if suspend else 'ACTIVE'}").consume()
            print(f"  {'suspended' if suspend else 'activated'} {login}")


def main(argv: list[str] | None = None) -> int:
    kb.utf8_output()
    ap = argparse.ArgumentParser(prog="kb_users.py", description="Manage the KB logins, as the admin.")
    ap.add_argument("command", choices=["add", "remove", "set-password", "remove-shared", "create", "suspend-writer",
                                        "activate-writer", "show"])
    ap.add_argument("names", nargs="*", help="first names for add / remove / set-password (or login names for set-password)")
    ap.add_argument("--yes", action="store_true", help="required to change users on production")
    args = ap.parse_args(argv)
    try:
        for n in args.names:            # validate before connecting
            password_targets(n) if args.command == "set-password" else person_logins(n)
        admin = migrate.admin_connection()
        if args.command != "show" and migrate.is_production(admin.host) and not args.yes:
            raise kb.KbError(f"{admin.host} is production: add --yes")
        if args.command == "remove-shared" and not migrate.is_production(admin.host):
            raise kb.KbError(f"{admin.host} isn't production: staging keeps the shared logins for the integration tests")
        with kb.driver(admin) as drv, drv.session(database="system") as s:
            print(f"{admin.host}:")
            run(args.command, s, args.names)
            rows = users(s)
            for r in rows:
                status = {True: "SUSPENDED", False: "active"}.get(r.get("suspended"), "status not shown")
                print(f"  {r['user']}: roles {sorted(r.get('roles') or [])}, {status}")
            for login in roleless(rows):
                print(f"  WARNING: {login} has no reader or publisher role; run add again for that person")
    except kb.KbError as e:
        print(f"kb_users.py: {e}", file=sys.stderr)
        return 2
    except Forbidden:
        print(f"kb_users.py: {admin.user} can't manage users on {admin.host} (Neo4j's admin role is needed). Use the "
              "instance admin: $env:COLOSSUS_KB_ADMIN_USER = 'neo4j' and its password (graph/admin/README.md)",
              file=sys.stderr)
        return 2
    except AuthError:
        print(f"kb_users.py: {admin.host} refused the login {admin.user}: check COLOSSUS_KB_ADMIN_USER and "
              "_PASSWORD in this session", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
