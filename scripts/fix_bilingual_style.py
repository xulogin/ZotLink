# -*- coding: utf-8 -*-
"""Turn on a GB/T 7714 style's bilingual (等 / et al.) switch.

The problem it fixes
--------------------
GB/T 7714-2015 wants the "and others" term to follow the *reference's own*
language: 中文文献 → 等, English references → et al. The GB/T styles shipped
with Zotero implement this with CSL-M multi-layout, but ship it **commented
out**, so every reference gets 等 — including the English ones.

What this does
--------------
Reads an installed .csl, uncomments the `<layout ... locale="en">` blocks,
gives the result a new id + title, and installs it alongside the original as
a separate style. Your original style file is never modified.

The switch only fires for items whose Zotero `language` field looks like
English (`en`, `en-US`, …). Run `zot_language.py` first to see whether yours
are set; an English item with an empty language field still renders 等.

Run:
  python scripts/fix_bilingual_style.py --list        # 有哪些样式可以修
  python scripts/fix_bilingual_style.py               # 修 Zotero 当前用的那个
  python scripts/fix_bilingual_style.py --style china-national-standard-gb-t-7714-2015-author-date
  python scripts/fix_bilingual_style.py --out-only    # 只写到当前目录，不装进 Zotero
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

zot_env.force_utf8()

# <!-- <layout ... locale="en"> ... </layout>  -->
COMMENTED_LAYOUT = re.compile(
    r"<!--\s*(<layout\b[^>]*\blocale=\"en\"[^>]*>.*?</layout>)\s*-->", re.DOTALL)
# the Chinese hint line the style author left above each block
HINT = re.compile(r"[ \t]*<!--\s*取消这部分注释[^>]*-->\s*\n?")

SUFFIX = "-zotlink-bilingual"


def styles_dir():
    d = zot_env.find_data_dir({}) / "styles"
    if not d.is_dir():
        sys.exit("FATAL: {} not found — is this the right Zotero data directory?".format(d))
    return d


def candidates(d):
    out = []
    for p in sorted(d.glob("*.csl")):
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if COMMENTED_LAYOUT.search(t):
            out.append(p)
    return out


def style_title(text):
    m = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
    return m.group(1).strip() if m else "(untitled)"


def patch(text):
    """Uncomment the CSL-M layouts; return (new_text, count)."""
    new, n = COMMENTED_LAYOUT.subn(lambda m: m.group(1), text)
    if n:
        new = HINT.sub("", new)
    return new, n


def rebrand(text, stem):
    """Give the patched style its own identity so Zotero lists it separately."""
    new_id = "https://github.com/xulogin/ZotLink/styles/" + stem + SUFFIX
    text = re.sub(r"<id>.*?</id>", "<id>{}</id>".format(new_id), text, count=1, flags=re.DOTALL)
    text = re.sub(r"<title>(.*?)</title>",
                  lambda m: "<title>{}（双语 等/et al.）</title>".format(m.group(1).strip()),
                  text, count=1, flags=re.DOTALL)
    # A self link pointing at the original would make Zotero treat them as one
    text = re.sub(r'<link href="[^"]*" rel="self"/>',
                  '<link href="{}" rel="self"/>'.format(new_id), text, count=1)
    return text, new_id


def main():
    args = sys.argv[1:]
    d = styles_dir()
    cands = candidates(d)

    if "--list" in args:
        print("可以开启双语开关的样式（在 {}）：".format(d))
        for p in cands:
            print("  - {}\n      {}".format(p.name, style_title(p.read_text(encoding="utf-8"))))
        if not cands:
            print("  （没找到带 CSL-M 注释块的样式）")
        return 0

    # which style?
    want = None
    if "--style" in args:
        want = args[args.index("--style") + 1]
    else:
        last = zot_env.last_style_id()
        if last:
            want = last.rstrip("/").split("/")[-1]
            print("Zotero 当前样式：{}".format(last))

    target = None
    if want:
        for p in cands:
            if p.stem == want or p.name == want:
                target = p
                break
        if target is None:
            for p in d.glob("*.csl"):
                if p.stem == want or p.name == want:
                    sys.exit("FATAL: {} 里没有被注释的 CSL-M 布局 —— 它要么已经是双语的，"
                             "要么不支持这个开关。\n       用 --list 看哪些能修。".format(p.name))
            sys.exit("FATAL: 找不到样式 {}。用 --list 看可选项。".format(want))
    elif len(cands) == 1:
        target = cands[0]
    else:
        sys.exit("FATAL: 有 {} 个候选样式，用 --style <名字> 指定；--list 看列表。".format(len(cands)))

    src = target.read_text(encoding="utf-8")
    print("源样式：{}\n        {}".format(target.name, style_title(src)))

    new, n = patch(src)
    if not n:
        sys.exit("FATAL: 没找到可以取消注释的布局 —— 这个样式可能已经是双语的了")
    new, new_id = rebrand(new, target.stem)

    try:
        ET.fromstring(new)
    except ET.ParseError as e:
        sys.exit("FATAL: 补丁后 XML 不合法，已中止，没有写任何文件：{}".format(e))

    print("  打开了 {} 个 locale=\"en\" 布局（正文引用 + 参考文献表）".format(n))
    print("  新标题：{}".format(style_title(new)))
    print("  新 id  ：{}".format(new_id))

    out_name = target.stem + SUFFIX + ".csl"
    if "--out-only" in args:
        out = Path.cwd() / out_name
    else:
        out = d / out_name
    if out.resolve() == target.resolve():
        sys.exit("FATAL: 拒绝覆盖原样式")
    out.write_text(new, encoding="utf-8")
    print("\n写入 {}".format(out))

    if "--out-only" not in args:
        print("\n接下来（这两步脚本代劳不了，都是 GUI）：")
        print("  1. 完全退出 Zotero 再重开（样式列表只在启动时扫描）")
        print("  2. Word → Zotero → Document Preferences → 选")
        print("     「{}」→ OK".format(style_title(new)))
        print("  3. Refresh，英文文献应该变成 et al.，中文文献仍然是 等")
        print("\n不想要了就删掉这个文件：{}".format(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
