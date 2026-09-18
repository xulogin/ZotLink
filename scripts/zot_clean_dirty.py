# -*- coding: utf-8 -*-
"""Delete the dirty fields flagged by zot_scan_dirty.py from zotero.sqlite.

This is the only script in the pipeline that WRITES to your Zotero library,
so it is deliberately paranoid:
  - refuses to run unless it can take an exclusive lock (i.e. Zotero is closed)
  - makes a timestamped backup of zotero.sqlite before touching anything
  - single transaction, rollback on any error
  - prints a dry-run summary and asks for confirmation (unless --yes)

Run:
  1. Close Zotero completely (check Task Manager for a stray zotero.exe).
  2. python scripts/zot_clean_dirty.py [--project DIR] [--yes]
  3. Re-open Zotero, then in Word: Zotero ribbon -> Refresh.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402


def main():
    proj, args = zot_env.open_project()
    db = proj.db()

    if not proj.dirty_plan.exists():
        print("FATAL: {} not found — run zot_scan_dirty.py first".format(proj.dirty_plan),
              file=sys.stderr)
        return 1
    plan = json.loads(proj.dirty_plan.read_text(encoding="utf-8"))
    if not plan:
        print("Nothing to clean — plan is empty.")
        return 0

    # 1. Lock check. Zotero holds the DB open while running; writing underneath
    #    it corrupts the library, so this gate is not optional.
    if zot_env.zotero_alive():
        print("FATAL: Zotero is still running (connector answered on :{}). "
              "Close it and re-run.".format(zot_env.CONNECTOR_PORT), file=sys.stderr)
        return 1
    try:
        probe = sqlite3.connect(str(db), timeout=2)
        probe.execute("BEGIN IMMEDIATE")
        probe.execute("ROLLBACK")
        probe.close()
    except sqlite3.OperationalError as e:
        print("FATAL: cannot lock {} — is Zotero still running?\n  {}".format(db, e),
              file=sys.stderr)
        return 1

    # 2. Backup
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = db.with_name("zotero.sqlite.bak-{}".format(ts))
    shutil.copy2(db, backup)
    print("[backup] {}  ({:,} bytes)".format(backup, backup.stat().st_size))

    # 3. Resolve field names -> IDs
    conn = sqlite3.connect(str(db), timeout=5)
    cur = conn.cursor()
    field_ids = {}
    for entry in plan:
        for fname in entry["fieldsToDelete"]:
            if fname in field_ids:
                continue
            cur.execute("SELECT fieldID FROM fields WHERE fieldName=?", (fname,))
            row = cur.fetchone()
            if not row:
                print("FATAL: unknown field {}".format(fname), file=sys.stderr)
                conn.close()
                return 1
            field_ids[fname] = row[0]

    # 4. Dry-run preview
    print("\nWill delete dirty fields from {} item(s):".format(len(plan)))
    for entry in plan:
        print("  - {:30s}  itemKey={}  fields: {}".format(
            entry["citekey"], entry["itemKey"], entry["fieldsToDelete"]))

    if "--yes" in args:
        print("\n[--yes set, skipping interactive confirmation]")
    else:
        confirm = input("\nProceed? type `yes` to apply, anything else to abort: ")
        if confirm.strip().lower() != "yes":
            print("aborted; no changes made.")
            conn.close()
            return 0

    # 5. Apply in a single transaction
    try:
        cur.execute("BEGIN")
        affected = 0
        for entry in plan:
            iid = entry["itemID"]
            for fname in entry["fieldsToDelete"]:
                cur.execute("DELETE FROM itemData WHERE itemID=? AND fieldID=?",
                            (iid, field_ids[fname]))
                affected += cur.rowcount
            cur.execute("UPDATE items SET clientDateModified=CURRENT_TIMESTAMP, "
                        "version=version+1 WHERE itemID=?", (iid,))
        cur.execute("COMMIT")
        print("\n[done] {} row(s) removed across {} item(s).".format(affected, len(plan)))
    except Exception as e:
        cur.execute("ROLLBACK")
        print("FATAL: rolled back due to {}".format(e), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("\nNext steps:")
    print("  1. Re-open Zotero.")
    print("  2. Spot-check the items — the flagged fields should be empty.")
    print("  3. In Word: Zotero ribbon -> Refresh.")
    print("\nIf anything looks wrong, restore from backup:")
    print('  copy /Y "{}" "{}"'.format(backup, db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
