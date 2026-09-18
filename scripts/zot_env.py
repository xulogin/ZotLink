# -*- coding: utf-8 -*-
"""Shared environment / config resolution for the ZotLink pipeline.

Everything machine-specific lives here so the other scripts stay portable:
  - where zotero.sqlite is          (auto-detected from Zotero's prefs.js)
  - which library URI prefix to use (local key vs. synced userID)
  - how to reach the Zotero connector without tripping over an HTTP proxy
  - where the current manuscript project root is

Resolution order for every setting: CLI arg > environment variable >
<project>/zotlink.json > auto-detection > built-in default.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

CONNECTOR_PORT = 23119
PING_URL = "http://127.0.0.1:{}/connector/ping".format(CONNECTOR_PORT)
IMPORT_URL = "http://127.0.0.1:{}/connector/import".format(CONNECTOR_PORT)

CONFIG_NAME = "zotlink.json"
_PROJECT_MARKERS = (CONFIG_NAME, "data/references.bib", "content")


# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------
def force_utf8() -> None:
    """Windows consoles default to GBK and choke on ✓ / → in output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# project root
# ---------------------------------------------------------------------------
def find_project_root(explicit=None):
    """Locate the manuscript project root.

    `explicit` (from --project) wins. Otherwise walk up from CWD until a
    directory looks like a project (has zotlink.json, or data/references.bib,
    or a content/ directory).
    """
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            sys.exit("FATAL: --project {} is not a directory".format(root))
        return root

    env = os.environ.get("ZOTLINK_PROJECT")
    if env:
        return Path(env).expanduser().resolve()

    here = Path.cwd().resolve()
    for cand in [here] + list(here.parents):
        if (cand / CONFIG_NAME).exists():
            return cand
        if (cand / "data" / "references.bib").exists():
            return cand
        if (cand / "content").is_dir() and (cand / "data").is_dir():
            return cand
    sys.exit(
        "FATAL: no ZotLink project found at or above {}\n"
        "       cd into a project directory, pass --project <dir>, or create one:\n"
        "       python <skill>/scripts/new_project.py <dir>".format(here)
    )


def take_project_arg(argv):
    """Pop `--project X` / `--project=X` out of argv, return (root, rest)."""
    rest, explicit = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--project" and i + 1 < len(argv):
            explicit = argv[i + 1]
            i += 2
            continue
        if a.startswith("--project="):
            explicit = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    return find_project_root(explicit), rest


# ---------------------------------------------------------------------------
# config file
# ---------------------------------------------------------------------------
def load_config(root: Path) -> dict:
    cfg_path = root / CONFIG_NAME
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:  # a broken config should never be silently ignored
        sys.exit("FATAL: cannot parse {}: {}".format(cfg_path, e))


# ---------------------------------------------------------------------------
# Zotero data directory
# ---------------------------------------------------------------------------
def _prefs_candidates():
    """Zotero profile prefs.js locations, per platform."""
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    roots = []
    if appdata:
        roots.append(Path(appdata) / "Zotero" / "Zotero" / "Profiles")
    roots.append(home / "Library" / "Application Support" / "Zotero" / "Profiles")
    roots.append(home / ".zotero" / "zotero")
    for r in roots:
        if r.is_dir():
            for prof in sorted(r.iterdir()):
                p = prof / "prefs.js"
                if p.exists():
                    yield p


def _data_dir_from_prefs():
    pat = re.compile(r'user_pref\("extensions\.zotero\.dataDir",\s*"(.*?)"\s*\)')
    for prefs in _prefs_candidates():
        try:
            text = prefs.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        m = pat.search(text)
        if m:
            # prefs.js stores Windows paths with escaped backslashes
            return Path(m.group(1).replace("\\\\", "\\"))
    return None


def last_style_id(cfg=None):
    """The CSL style id Zotero used last, from prefs.js (None if unknown)."""
    pat = re.compile(r'user_pref\("extensions\.zotero\.export\.lastStyle",\s*"(.*?)"\s*\)')
    for prefs in _prefs_candidates():
        try:
            m = pat.search(prefs.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if m:
            return m.group(1)
    return None


def find_data_dir(cfg=None):
    """Zotero data directory (the folder holding zotero.sqlite)."""
    cfg = cfg or {}
    for cand in (os.environ.get("ZOTERO_DATA_DIR"), cfg.get("zotero_data_dir")):
        if cand:
            return Path(cand).expanduser()
    auto = _data_dir_from_prefs()
    if auto and (auto / "zotero.sqlite").exists():
        return auto
    default = Path.home() / "Zotero"
    if (default / "zotero.sqlite").exists():
        return default
    return auto or default


def find_db(cfg=None) -> Path:
    db = find_data_dir(cfg) / "zotero.sqlite"
    if not db.exists():
        sys.exit(
            "FATAL: zotero.sqlite not found at {}\n"
            "       Set it explicitly, either way works:\n"
            '         - "zotero_data_dir": "D:/Zotero" in your project\'s {}\n'
            "         - set ZOTERO_DATA_DIR=D:\\Zotero\n"
            "       (Zotero → Edit → Settings → Advanced shows the real location.)"
            .format(db, CONFIG_NAME)
        )
    return db


# ---------------------------------------------------------------------------
# read-only SQLite access (safe while Zotero is running)
# ---------------------------------------------------------------------------
def connect_ro(db: Path):
    """Open zotero.sqlite read-only.

    nolock=1 lets us read while Zotero holds the file. If that still fails
    (or the DB is mid-WAL-checkpoint), fall back to reading a temp copy.
    """
    uri = "file:{}?mode=ro&immutable=0&nolock=1".format(db.as_posix())
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.execute("SELECT COUNT(*) FROM items").fetchone()
        return conn
    except sqlite3.Error:
        tmp = Path(tempfile.mkdtemp(prefix="zotlink-")) / "zotero.sqlite"
        shutil.copy2(db, tmp)
        for suffix in ("-wal", "-shm"):
            side = db.with_name(db.name + suffix)
            if side.exists():
                shutil.copy2(side, tmp.with_name(tmp.name + suffix))
        print("  [db] live read failed, using snapshot at {}".format(tmp))
        return sqlite3.connect(str(tmp), timeout=5)


# ---------------------------------------------------------------------------
# library identity → the URI prefix baked into docx citation fields
# ---------------------------------------------------------------------------
def library_uri_prefix(conn, cfg=None) -> str:
    """Return e.g. 'http://zotero.org/users/local/AbCdEf12/items/'.

    A synced account uses the numeric userID instead of the local key; Zotero
    writes both into the `settings` table, so prefer whichever is present in
    the same order Zotero itself resolves them.
    """
    cfg = cfg or {}
    override = os.environ.get("ZOTLINK_URI_PREFIX") or cfg.get("library_uri_prefix")
    if override:
        return override.rstrip("/") + "/"

    cur = conn.cursor()
    vals = {}
    try:
        cur.execute("SELECT key, value FROM settings WHERE setting='account'")
        vals = {k: v for k, v in cur.fetchall()}
    except sqlite3.Error:
        pass

    user_id = vals.get("userID")
    if user_id:
        return "http://zotero.org/users/{}/items/".format(str(user_id).strip('"'))
    local_key = vals.get("localUserKey")
    if local_key:
        return "http://zotero.org/users/local/{}/items/".format(str(local_key).strip('"'))
    sys.exit(
        "FATAL: could not read localUserKey/userID from zotero.sqlite settings.\n"
        '       Set "library_uri_prefix" in {} if you know it.'.format(CONFIG_NAME)
    )


def user_library_id(conn) -> int:
    cur = conn.cursor()
    try:
        cur.execute("SELECT libraryID FROM libraries WHERE type='user'")
        row = cur.fetchone()
        if row:
            return int(row[0])
    except sqlite3.Error:
        pass
    return 1


# ---------------------------------------------------------------------------
# Zotero connector (localhost — must bypass any system HTTP proxy)
# ---------------------------------------------------------------------------
def local_opener():
    """urllib opener with proxies disabled.

    Without this, an HTTP_PROXY env var (common on machines using a VPN or a
    clash-style local proxy) makes urllib route 127.0.0.1:23119 through the
    proxy, which answers 502 and looks exactly like "Zotero is not running".
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def zotero_alive(timeout: float = 3.0) -> bool:
    try:
        with local_opener().open(PING_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# paths within a project
# ---------------------------------------------------------------------------
class Project(object):
    def __init__(self, root: Path):
        self.root = root
        self.data = root / "data"
        self.content = root / "content"
        self.reports = root / "reports"
        self.output = root / "output"
        self.bib = self.data / "references.bib"
        self.csl_json = self.data / "references.json"
        self.match_index = self.reports / "zot_match_index.json"
        self.match_report = self.reports / "zot_match_report.md"
        self.dirty_report = self.reports / "zot_dirty_report.md"
        self.dirty_plan = self.reports / "zot_dirty_plan.json"
        self.missing_bib = self.reports / "references_missing.bib"
        self.cfg = load_config(root)

    def ensure_dirs(self) -> None:
        for d in (self.data, self.content, self.reports, self.output):
            d.mkdir(parents=True, exist_ok=True)

    def db(self) -> Path:
        return find_db(self.cfg)


def open_project(argv=None):
    """Standard entry point for every script: returns (Project, remaining_argv)."""
    force_utf8()
    root, rest = take_project_arg(list(argv if argv is not None else sys.argv[1:]))
    return Project(root), rest
