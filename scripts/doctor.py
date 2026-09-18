# -*- coding: utf-8 -*-
"""Self-check for the ZotLink pipeline: prints what is present, what is
missing, and exactly what to do about it.

Run:  python scripts/doctor.py [--project DIR]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

zot_env.force_utf8()

OK, BAD, WARN = "[ ok ]", "[FAIL]", "[warn]"
failures = []


def check(label, ok, detail="", fix="", fatal=True):
    print("{} {}{}".format(OK if ok else (BAD if fatal else WARN), label,
                           "  " + detail if detail else ""))
    if not ok:
        if fix:
            print("       -> {}".format(fix))
        if fatal:
            failures.append(label)
    return ok


print("=" * 64)
print("  ZotLink doctor")
print("=" * 64)

# --- python ----------------------------------------------------------------
check("Python {}.{}.{}".format(*sys.version_info[:3]),
      sys.version_info >= (3, 8), sys.executable,
      "Python 3.8 or newer is required")

# --- python-docx -----------------------------------------------------------
try:
    import docx  # noqa: F401
    check("python-docx", True, docx.__file__)
except ImportError:
    check("python-docx", False, "", "pip install python-docx")

# --- pandoc ----------------------------------------------------------------
pandoc = shutil.which("pandoc")
check("pandoc", bool(pandoc), pandoc or "",
      "install from https://pandoc.org/installing.html and reopen the terminal")

# --- Zotero database -------------------------------------------------------
cfg = {}
root = None
try:
    root, _ = zot_env.take_project_arg(sys.argv[1:])
    cfg = zot_env.load_config(root)
    print("{} project  {}".format(OK, root))
except SystemExit:
    print("{} project  (none — run this from a project dir to check it too)".format(WARN))

data_dir = zot_env.find_data_dir(cfg)
db = data_dir / "zotero.sqlite"
db_ok = check("zotero.sqlite", db.exists(), str(db),
              'set ZOTERO_DATA_DIR, or "zotero_data_dir" in zotlink.json')

if db_ok:
    try:
        conn = zot_env.connect_ro(db)
        cur = conn.cursor()
        n = cur.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        check("library readable", True, "{} items".format(n))
        prefix = zot_env.library_uri_prefix(conn, cfg)
        check("library URI prefix", True, prefix + "<itemKey>")
        conn.close()
    except Exception as e:
        check("library readable", False, str(e),
              "close Zotero and retry, or check the data directory path")

# --- connector -------------------------------------------------------------
alive = zot_env.zotero_alive()
check("Zotero connector :{}".format(zot_env.CONNECTOR_PORT), alive,
      "reachable" if alive else "no response",
      "start Zotero (only needed to auto-import new references); "
      "Settings -> Advanced -> allow local applications",
      fatal=False)

# --- project layout --------------------------------------------------------
if root:
    proj = zot_env.Project(root)
    check("data/references.bib", proj.bib.exists(), str(proj.bib),
          "create it, or scaffold a project with scripts/new_project.py",
          fatal=False)
    mds = sorted(proj.content.glob("*.md")) if proj.content.is_dir() else []
    check("content/*.md", bool(mds),
          ", ".join(m.name for m in mds) if mds else "",
          "write your manuscript in content/", fatal=False)

print("=" * 64)
if failures:
    print("  {} blocking problem(s): {}".format(len(failures), ", ".join(failures)))
    sys.exit(1)
print("  all required checks passed")
sys.exit(0)
