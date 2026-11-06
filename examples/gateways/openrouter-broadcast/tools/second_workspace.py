#!/usr/bin/env python3
"""LOCAL TEST STACK ONLY. Make a second workspace and key in a self-hosted Future AGI, to prove that a key
cannot write into another workspace's project. Works by writing rows into the stack's Postgres (through
`docker exec`), so it is not for a real deployment.

  second_workspace.py create --out creds.json     second workspace + a key bound to it (file is mode 0600)
  second_workspace.py counts --name MY-PROJECT    projects with that name per workspace, and their span counts
  second_workspace.py remove                      soft-delete the key, its projects and the workspace

Containers default to the TH-8103 local stack; change them with FI_PG_CONTAINER and FI_CH_CONTAINER.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import uuid

PG = os.environ.get("FI_PG_CONTAINER", "th8103-e2e-postgres-1")
CH = os.environ.get("FI_CH_CONTAINER", "th8103-e2e-clickhouse-1")
WS_NAME = "th8103-rest-ob-ws2"
KEY_NAME = "th8103-rest-ob-ws2-key"


def pg(sql):
    out = subprocess.run(["docker", "exec", PG, "psql", "-U", "futureagi", "-d", "futureagi", "-Atc", sql], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"postgres error: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def ch(sql):
    out = subprocess.run(["docker", "exec", CH, "clickhouse-client", "-q", sql], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"clickhouse error: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def create(out_path):
    remove(quiet=True)
    ws, key = str(uuid.uuid4()), str(uuid.uuid4())
    api, secret = secrets.token_hex(16), secrets.token_hex(16)
    pg(f"""INSERT INTO accounts_workspace (created_at, updated_at, deleted, id, name, display_name, description, is_active, is_default, created_by_id, organization_id)
           SELECT now(), now(), false, '{ws}', '{WS_NAME}', '{WS_NAME}', '', true, false, created_by_id, organization_id
           FROM accounts_workspace WHERE is_default AND NOT deleted AND is_active LIMIT 1""")
    pg(f"""INSERT INTO accounts_orgapikey (created_at, updated_at, deleted, id, name, api_key, secret_key, type, enabled, organization_id, user_id, workspace_id)
           SELECT now(), now(), false, '{key}', '{KEY_NAME}', '{api}', '{secret}', 'user', true, organization_id, created_by_id, id
           FROM accounts_workspace WHERE id = '{ws}'""")
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"workspace_id": ws, "api_key": api, "secret_key": secret}, f)
    print(f"created workspace {WS_NAME} ({ws}) and a key bound to it; credentials in {out_path}")


def counts(name):
    safe = name.replace("'", "''")
    rows = pg(f"""SELECT p.id, p.workspace_id, w.name FROM tracer_project p JOIN accounts_workspace w ON w.id = p.workspace_id
                  WHERE p.name = '{safe}' AND NOT p.deleted ORDER BY w.name""")
    result = []
    for line in rows.splitlines():
        pid, wid, wname = line.split("|")
        n = ch(f"SELECT count() FROM spans FINAL WHERE project_id = '{pid}' AND is_deleted = 0")
        result.append({"workspace": wname, "workspace_id": wid, "project_id": pid, "spans": int(n)})
        print(f"  workspace {wname!r:28} project {pid}  spans={n}")
    if not result:
        print("  no project with that name")
    return result


def remove(quiet=False):
    ws = pg(f"SELECT id FROM accounts_workspace WHERE name='{WS_NAME}' AND NOT deleted")
    if not ws:
        if not quiet:
            print("nothing to remove")
        return
    pg(f"UPDATE tracer_project SET deleted = true WHERE workspace_id = '{ws}'")
    pg(f"UPDATE accounts_orgapikey SET deleted = true, enabled = false, deleted_at = now() WHERE name = '{KEY_NAME}'")
    pg(f"UPDATE accounts_workspace SET deleted = true, is_active = false, deleted_at = now(), name = name || '-' || left(id::text, 8) WHERE id = '{ws}'")
    pg(f"UPDATE accounts_orgapikey SET name = name || '-' || left(id::text, 8) WHERE name = '{KEY_NAME}'")
    if not quiet:
        print(f"soft-deleted workspace {WS_NAME}, its key and its projects")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create"); c.add_argument("--out", required=True)
    n = sub.add_parser("counts"); n.add_argument("--name", required=True)
    sub.add_parser("remove")
    a = ap.parse_args()
    if a.cmd == "create":
        create(a.out)
    elif a.cmd == "counts":
        counts(a.name)
    else:
        remove()
    return 0


if __name__ == "__main__":
    sys.exit(main())
