# -*- coding: utf-8 -*-
"""End-to-end orchestrator for the ZotLink (Zotero <-> docx) pipeline.

Steps, in order, skipping whatever is already up to date:
  1. pandoc  data/references.bib -> data/references.json   (only if bib is newer)
  2. zot_match.py        map every citekey to a real Zotero itemKey
  3. if miss > 0         POST reports/references_missing.bib to Zotero's
                         /connector/import (stock Zotero 7/8, no Better BibTeX
                         needed), then re-match; otherwise tell the user what
                         to import by hand
  4. zot_scan_dirty.py   flag aggregator junk in the matched items
  5. if dirty > 0        stop and tell the user to close Zotero and clean,
                         or do it automatically with --auto-clean
  6. build_doc.py        write output/<name>.docx

Usage:
  python scripts/run.py [--project DIR] [--auto-clean] [--skip-dirty] [content/my.md]

Exit codes:
  0 = done, or "do the manual step then re-run"
  1 = unrecoverable error
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zot_env  # noqa: E402

PROJ, ARGS = zot_env.open_project()
AUTO_CLEAN = "--auto-clean" in ARGS
SKIP_DIRTY = "--skip-dirty" in ARGS
MD_ARGS = [a for a in ARGS if not a.startswith("--")]


def step(title):
    print("\n{}\n  {}\n{}".format("=" * 60, title, "=" * 60))


def run_py(name, *extra):
    return subprocess.run(
        [sys.executable, str(HERE / name), "--project", str(PROJ.root)] + list(extra),
        cwd=str(PROJ.root), text=True, encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 1. pandoc bib -> json (only when the bib is newer)
# ---------------------------------------------------------------------------
def pandoc_if_needed():
    step("1. pandoc references.bib -> references.json")
    if not PROJ.bib.exists():
        sys.exit("FATAL: {} not found".format(PROJ.bib))
    if PROJ.csl_json.exists() and PROJ.csl_json.stat().st_mtime >= PROJ.bib.stat().st_mtime:
        print("  json is up to date, skipping pandoc")
        return
    if not shutil.which("pandoc"):
        sys.exit("FATAL: pandoc not found in PATH — https://pandoc.org/installing.html")
    r = subprocess.run(["pandoc", str(PROJ.bib), "-t", "csljson", "-o", str(PROJ.csl_json)],
                       text=True)
    if r.returncode != 0:
        sys.exit("FATAL: pandoc failed — check the BibTeX syntax in {}".format(PROJ.bib))
    print("  wrote {}".format(PROJ.csl_json))


# ---------------------------------------------------------------------------
# 2. zot_match
# ---------------------------------------------------------------------------
def zot_match():
    step("2. zot_match — references.bib <-> Zotero library")
    r = run_py("zot_match.py")
    if r.returncode != 0:
        sys.exit("FATAL: zot_match.py failed")
    with open(PROJ.csl_json, encoding="utf-8") as f:
        total = len(set(i["id"] for i in json.load(f)))
    with open(PROJ.match_index, encoding="utf-8") as f:
        matched = len(json.load(f))
    miss = total - matched
    print("  -> matched {}/{}, miss={}".format(matched, total, miss))
    return {"total": total, "matched": matched, "miss": miss}


# ---------------------------------------------------------------------------
# 3. Auto-import the missing entries through Zotero's standard connector.
#    No Better BibTeX required — stock Zotero 7/8 accepts raw BibTeX here.
# ---------------------------------------------------------------------------
def import_missing_via_connector(missing_bib: Path) -> bool:
    if not missing_bib.exists():
        print("  no references_missing.bib produced — nothing importable")
        return False

    req = urllib.request.Request(
        "{}?session={}".format(zot_env.IMPORT_URL, secrets.token_hex(16)),
        method="POST",
        headers={"Content-Type": "application/x-bibtex",
                 "Zotero-Allowed-Request": "true"},
        data=missing_bib.read_bytes(),
    )
    try:
        with zot_env.local_opener().open(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status not in (200, 201):
                print("  connector returned HTTP {}".format(resp.status))
                return False
            try:
                items = json.loads(body)
            except ValueError:
                print("  connector responded non-JSON: {}".format(body[:200]))
                return False
            print("  Zotero imported {} item(s):".format(len(items)))
            for it in items:
                print("      [{}] {}".format(it.get("key", "?"), (it.get("title") or "?")[:60]))
            return True
    except urllib.error.HTTPError as e:
        print("  connector HTTP {}: {}".format(
            e.code, e.read().decode("utf-8", errors="replace")[:200]))
        return False
    except Exception as e:
        print("  connector call failed: {}".format(e))
        return False


def handle_missing(stats):
    """Return True if the user must act and re-run."""
    step("3. handle {} missing entr(y/ies)".format(stats["miss"]))

    if zot_env.zotero_alive():
        print("  Zotero is running — importing via /connector/import")
        if import_missing_via_connector(PROJ.missing_bib):
            print("  re-running zot_match to confirm")
            if zot_match()["miss"] == 0:
                print("  all entries matched")
                return False
            print("  still missing after import — see the report")
    else:
        print("  Zotero is not reachable on 127.0.0.1:{}".format(zot_env.CONNECTOR_PORT))
        print("  (start Zotero; if it is already open, enable Settings -> Advanced ->")
        print("   'Allow other applications on this computer to communicate with Zotero')")

    print("\n  MANUAL ACTION NEEDED:")
    print("     1. Start Zotero and re-run this script, or")
    print("     2. Zotero: File -> Import -> A file, select")
    print("        {}".format(PROJ.missing_bib))
    print("     3. Re-run:  python scripts/run.py --project \"{}\"".format(PROJ.root))
    return True


# ---------------------------------------------------------------------------
# 4-5. dirty scan / clean
# ---------------------------------------------------------------------------
def zot_scan():
    step("4. zot_scan_dirty — look for aggregator junk fields")
    r = run_py("zot_scan_dirty.py")
    if r.returncode != 0:
        sys.exit("FATAL: zot_scan_dirty.py failed")
    return len(json.loads(PROJ.dirty_plan.read_text(encoding="utf-8")))


def handle_dirty(dirty_count):
    """Return True if the user must act and re-run."""
    step("5. handle {} dirty item(s)".format(dirty_count))
    print("  details: {}".format(PROJ.dirty_report))
    if not AUTO_CLEAN:
        print("\n  MANUAL ACTION NEEDED (or re-run with --auto-clean):")
        print("     1. Close Zotero completely")
        print("     2. python scripts/zot_clean_dirty.py --project \"{}\" --yes".format(PROJ.root))
        print("     3. Re-open Zotero, re-run:  python scripts/run.py")
        print("\n  Or pass --skip-dirty to build anyway (the junk will show up in")
        print("  the reference list after Refresh).")
        return True
    if zot_env.zotero_alive():
        print("  Zotero is still running — close it, then re-run with --auto-clean")
        return True
    r = run_py("zot_clean_dirty.py", "--yes")
    if r.returncode != 0:
        sys.exit("FATAL: zot_clean_dirty.py failed")
    print("  cleaned")
    return False


# ---------------------------------------------------------------------------
# 6. build
# ---------------------------------------------------------------------------
def build():
    step("6. build_doc — generate the docx")
    r = run_py("build_doc.py", *MD_ARGS)
    if r.returncode != 0:
        sys.exit("FATAL: build_doc.py failed")


def main():
    print("[project]  {}".format(PROJ.root))
    PROJ.ensure_dirs()

    pandoc_if_needed()
    stats = zot_match()

    if stats["miss"] > 0:
        if handle_missing(stats):
            return 0

    if SKIP_DIRTY:
        print("\n[skip] dirty-field scan skipped (--skip-dirty)")
    else:
        dirty = zot_scan()
        if dirty > 0 and handle_dirty(dirty):
            return 0

    build()

    print("\n" + "=" * 60)
    print("  DONE — open output/*.docx, then in Word: Zotero -> Refresh")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
