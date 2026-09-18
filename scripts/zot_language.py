# -*- coding: utf-8 -*-
"""Audit (and optionally normalise) the `language` field of Zotero items.

Why this matters
----------------
A bilingual GB/T 7714 style picks 等 vs "et al." from each item's `language`
field, not from the title. An English paper with an empty (or non-standard)
language field falls through to the default layout and gets 等 — which is
wrong, and looks exactly like "the style is broken".

Real libraries are messy: 中文; / 英文; / english / (empty) are all common.
This script proposes a BCP-47-ish value per item — `zh` for CJK titles,
`en` otherwise — and only touches items whose current value cannot work.

Scan is read-only. Writes:
  reports/zot_lang_report.md    what is wrong and what it would become
  reports/zot_lang_plan.json    machine-readable plan for --fix

Run:
  python scripts/zot_language.py                    # scan matched items
  python scripts/zot_language.py --all              # scan the whole library
  python scripts/zot_language.py --fix              # apply (Zotero must be CLOSED)
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

PROJ, ARGS = zot_env.open_project()
PROJ.ensure_dirs()

SCAN_ALL = "--all" in ARGS
DO_FIX = "--fix" in ARGS
ASSUME_YES = "--yes" in ARGS

LANG_REPORT = PROJ.reports / "zot_lang_report.md"
LANG_PLAN = PROJ.reports / "zot_lang_plan.json"

# A value citeproc can actually match against a layout locale.
BCP47 = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def has_cjk(s):
    return bool(s) and any("㐀" <= c <= "鿿" for c in s)


# Free-text values real libraries actually contain. What the user wrote about
# the item beats guessing from the title — a Chinese-titled paper tagged 英文
# is their call, not ours.
KNOWN = {
    "中文": "zh", "中文;": "zh", "汉语": "zh", "简体中文": "zh",
    "chinese": "zh", "chi": "zh", "cn": "zh",
    "英文": "en", "英文;": "en", "english": "en", "eng": "en",
}


def proposed(title, current):
    """What the language field should be, or None to leave it alone."""
    cur = (current or "").strip()
    if cur and BCP47.match(cur):
        return None                       # en / en-US / zh-CN — already usable
    if cur:
        mapped = KNOWN.get(cur.lower().rstrip(";；, ").strip())
        if mapped:
            return mapped
    if not (title or "").strip():
        return None                       # no title, no evidence — don't guess
    return "zh" if has_cjk(title) else "en"


def load_targets(conn):
    cur = conn.cursor()
    if SCAN_ALL:
        cur.execute("""
            SELECT i.itemID, i.key,
              (SELECT v.value FROM itemData d JOIN fields f ON d.fieldID=f.fieldID
                JOIN itemDataValues v ON d.valueID=v.valueID
                WHERE d.itemID=i.itemID AND f.fieldName='title'),
              (SELECT v.value FROM itemData d JOIN fields f ON d.fieldID=f.fieldID
                JOIN itemDataValues v ON d.valueID=v.valueID
                WHERE d.itemID=i.itemID AND f.fieldName='language')
            FROM items i
            WHERE i.itemTypeID NOT IN
              (SELECT itemTypeID FROM itemTypes WHERE typeName IN ('attachment','note'))
              AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        """)
        return [(None, iid, key, t, lg) for iid, key, t, lg in cur.fetchall()]

    if not PROJ.match_index.exists():
        sys.exit("FATAL: {} not found — run scripts/zot_match.py first, "
                 "or pass --all to scan the whole library".format(PROJ.match_index))
    idx = json.loads(PROJ.match_index.read_text(encoding="utf-8"))
    rows = []
    for citekey, info in idx.items():
        cur.execute("""
            SELECT f.fieldName, v.value FROM itemData d
            JOIN fields f ON d.fieldID=f.fieldID
            JOIN itemDataValues v ON d.valueID=v.valueID
            WHERE d.itemID=? AND f.fieldName IN ('title','language')
        """, (info["itemID"],))
        got = dict(cur.fetchall())
        rows.append((citekey, info["itemID"], info["itemKey"],
                     got.get("title"), got.get("language")))
    return rows


def scan():
    conn = zot_env.connect_ro(PROJ.db())
    rows = load_targets(conn)
    conn.close()

    plan, ok = [], 0
    for citekey, iid, ikey, title, lang in rows:
        want = proposed(title, lang)
        if want is None:
            ok += 1
            continue
        plan.append({"citekey": citekey, "itemKey": ikey, "itemID": iid,
                     "title": (title or "")[:80], "current": lang, "proposed": want})

    scope = "整个库" if SCAN_ALL else "本项目引用到的条目"
    print("\n{}\nlanguage 字段体检（{}）：{} 条待修 / {} 条已可用\n{}"
          .format("=" * 70, scope, len(plan), ok, "=" * 70))

    lines = ["# Zotero language 字段体检",
             "\n范围：{}。**{} 条需要修正**，{} 条已经是可用的 BCP-47 值。\n".format(scope, len(plan), ok),
             "双语 GB/T 7714 样式靠这个字段决定输出 `等` 还是 `et al.`。",
             "值为空、或者写成 `中文;` / `english` 这种非标准形式，citeproc 匹配不上，",
             "会一律落到默认（中文）布局，英文文献也被打成「等」。\n",
             "| citekey | itemKey | 现值 | 建议 | 标题 |", "|---|---|---|---|---|"]
    for e in plan:
        lines.append("| {} | `{}` | `{}` | **{}** | {} |".format(
            e["citekey"] or "-", e["itemKey"],
            e["current"] if e["current"] else "(空)", e["proposed"],
            (e["title"] or "").replace("|", "\\|")))
    LANG_REPORT.write_text("\n".join(lines), encoding="utf-8")
    LANG_PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    for e in plan[:10]:
        print("  {:10s} {!r:12s} -> {:4s}  {}".format(
            e["itemKey"], e["current"], e["proposed"], (e["title"] or "")[:52]))
    if len(plan) > 10:
        print("  … 还有 {} 条，见报告".format(len(plan) - 10))

    print("\nreport -> {}".format(LANG_REPORT))
    print("plan   -> {}  ({} 条)".format(LANG_PLAN, len(plan)))
    return plan


def fix(plan):
    """Write the proposed values. Same safety bars as zot_clean_dirty.py."""
    if not plan:
        print("没有需要修的，跳过。")
        return 0

    db = PROJ.db()
    if zot_env.zotero_alive():
        print("FATAL: Zotero 还在跑（:{} 有响应）。完全关掉再来。"
              .format(zot_env.CONNECTOR_PORT), file=sys.stderr)
        return 1
    try:
        probe = sqlite3.connect(str(db), timeout=2)
        probe.execute("BEGIN IMMEDIATE")
        probe.execute("ROLLBACK")
        probe.close()
    except sqlite3.OperationalError as e:
        print("FATAL: 锁不住 {} —— Zotero 是不是还开着？\n  {}".format(db, e), file=sys.stderr)
        return 1

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = db.with_name("zotero.sqlite.bak-{}".format(ts))
    shutil.copy2(db, backup)
    print("[backup] {}  ({:,} bytes)".format(backup, backup.stat().st_size))

    print("\n将修改 {} 条的 language 字段：".format(len(plan)))
    for e in plan[:10]:
        print("  {:10s} {!r} -> {}".format(e["itemKey"], e["current"], e["proposed"]))
    if len(plan) > 10:
        print("  … 还有 {} 条".format(len(plan) - 10))

    if not ASSUME_YES:
        if input("\n执行？输入 `yes` 确认：").strip().lower() != "yes":
            print("已取消，未做任何修改。")
            return 0

    conn = sqlite3.connect(str(db), timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT fieldID FROM fields WHERE fieldName='language'")
    row = cur.fetchone()
    if not row:
        print("FATAL: 这个库里没有 language 字段定义", file=sys.stderr)
        conn.close()
        return 1
    field_id = row[0]

    try:
        cur.execute("BEGIN")
        changed = 0
        for e in plan:
            val = e["proposed"]
            cur.execute("SELECT valueID FROM itemDataValues WHERE value=?", (val,))
            got = cur.fetchone()
            if got:
                value_id = got[0]
            else:
                cur.execute("INSERT INTO itemDataValues (value) VALUES (?)", (val,))
                value_id = cur.lastrowid
            cur.execute("DELETE FROM itemData WHERE itemID=? AND fieldID=?",
                        (e["itemID"], field_id))
            cur.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?,?,?)",
                        (e["itemID"], field_id, value_id))
            cur.execute("UPDATE items SET clientDateModified=CURRENT_TIMESTAMP, "
                        "version=version+1 WHERE itemID=?", (e["itemID"],))
            changed += 1
        cur.execute("COMMIT")
        print("\n[done] 改了 {} 条。".format(changed))
    except Exception as e:
        cur.execute("ROLLBACK")
        print("FATAL: 已回滚，原因：{}".format(e), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("\n接下来：")
    print("  1. 重开 Zotero")
    print("  2. Word → Zotero → Refresh")
    print("\n要回滚：copy /Y \"{}\" \"{}\"".format(backup, db))
    return 0


def main():
    plan = scan()
    if DO_FIX:
        return fix(plan)
    if plan:
        print("\n只是体检，没动任何东西。要真改：")
        print("  1. 完全关掉 Zotero")
        print("  2. python scripts/zot_language.py{} --fix".format(" --all" if SCAN_ALL else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
