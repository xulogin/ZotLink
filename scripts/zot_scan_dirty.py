# -*- coding: utf-8 -*-
"""Scan the matched Zotero items for junk in series / seriesTitle / extra /
archive-ish fields.

Chinese aggregator translators (CNKI, 茉莉花/Jasminum, 中科院分区插件 ...) stuff
funding statements, ORCIDs, impact factors and quartile tags into these
fields. Every standard CSL style prints them verbatim, so a Refresh produces
references like "…, 基金项目: 国家自然科学基金, 中科院一区, 7.099Q1."

Read-only. Writes:
  reports/zot_dirty_report.md    what is dirty and why
  reports/zot_dirty_plan.json    machine-readable plan for zot_clean_dirty.py

Run:  python scripts/zot_scan_dirty.py [--project DIR]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

PROJ, _ = zot_env.open_project()
PROJ.ensure_dirs()

if not PROJ.match_index.exists():
    sys.exit("FATAL: {} not found — run scripts/zot_match.py first".format(PROJ.match_index))
idx = json.loads(PROJ.match_index.read_text(encoding="utf-8"))

# Marker words / patterns left behind by Chinese aggregator translators.
DIRTY_LITERAL = [
    "基金项目", "基金号", "ORCID", "姓名", "单位", "文献网站",
    "参考文献数量", "中科院", "中国科学院", "影响因子", "ＳＳＣＩ",
    "一区", "二区", "三区", "四区", "TOP", "【",
]
DIRTY_REGEX = [
    re.compile(r"\d+\.\d{2,4}\s*Q[1-4]"),   # "7.099Q1" impact-factor blob
    re.compile(r"Q[1-4][^A-Za-z]"),          # bare "Q1" followed by non-latin
]
DIRTY_FIELDS = ["series", "seriesTitle", "extra", "archive", "archiveLocation",
                "callNumber", "rights", "libraryCatalog", "shortTitle"]


def is_dirty(val):
    if not val:
        return False
    if any(lit in val for lit in DIRTY_LITERAL):
        return True
    return any(rx.search(val) for rx in DIRTY_REGEX)


conn = zot_env.connect_ro(PROJ.db())
cur = conn.cursor()

rows = []
for citekey, info in idx.items():
    cur.execute("""
      SELECT f.fieldName, v.value FROM itemData d
      JOIN fields f ON d.fieldID = f.fieldID
      JOIN itemDataValues v ON d.valueID = v.valueID
      WHERE d.itemID = ? AND f.fieldName IN ({})
    """.format(",".join("?" * len(DIRTY_FIELDS))), (info["itemID"], ) + tuple(DIRTY_FIELDS))
    fields = dict(cur.fetchall())
    dirty = dict((fname, val) for fname, val in fields.items() if is_dirty(val))
    if dirty:
        rows.append((citekey, info["itemKey"], info["itemID"], dirty))

print("\n{}\nDirty items: {} / {}\n{}\n".format("=" * 70, len(rows), len(idx), "=" * 70))
lines = [
    "# Zotero dirty-fields report",
    "\nScanned {} matched library items. Found **{} dirty item(s)**.".format(len(idx), len(rows)),
    "Each field below holds funding info, ORCIDs or Chinese aggregator",
    "metadata that standard CSL styles dump verbatim into the reference list.\n",
]
for citekey, ikey, iid, dirty in rows:
    print("--- {}  (itemKey={}, itemID={})".format(citekey, ikey, iid))
    lines.append("\n## `{}`  ·  itemKey `{}`  ·  itemID `{}`\n".format(citekey, ikey, iid))
    for fname, val in dirty.items():
        short = val[:200].replace("\n", " ")
        print("    [{}] {}".format(fname, short))
        lines.append("- **{}**: `{}{}`".format(fname, short, "..." if len(val) > 200 else ""))

PROJ.dirty_report.write_text("\n".join(lines), encoding="utf-8")
print("\nreport -> {}".format(PROJ.dirty_report))

plan = [{"citekey": ck, "itemKey": ik, "itemID": iid,
         "fieldsToDelete": sorted(dirty.keys())}
        for ck, ik, iid, dirty in rows]
PROJ.dirty_plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
print("plan   -> {}  ({} item(s))".format(PROJ.dirty_plan, len(plan)))

conn.close()
