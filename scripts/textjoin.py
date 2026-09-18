# -*- coding: utf-8 -*-
"""Soft-line-break joining rules for mixed Chinese/Latin manuscript text.

Kept in its own module (instead of inside build_doc.py) for one reason:
build_doc.py does real work at import time, so it cannot be imported by the
test harness. A wrong space between 汉字 produces a perfectly valid docx, so
verify_docx.py can never catch it — the only safety net is a unit test, and a
unit test needs something importable.
"""
from __future__ import annotations

import unicodedata


def char_class(ch):
    """ascii / punct (CJK-style punctuation) / han (everything else non-ASCII)."""
    if ch.isascii():
        return "ascii"
    if unicodedata.category(ch).startswith("P"):
        return "punct"
    return "han"


def needs_space(a, b):
    """Does a soft line break between `a` and `b` need a space?

      汉字 + 汉字            no space   plain Chinese wrapping
      任一侧是 CJK 标点       no space   “ ” 。 ， — … are NOT in the CJK blocks,
                                        so a block test wrongly adds a space
      汉字 + (Author, 2020)  space      盘古之白 — and citation markers land here
      汉字 + "…"             no space   an ASCII quote doing a Chinese quote's job
      Latin + Latin          space      ordinary English wrapping
    """
    if a.isspace() or b.isspace():
        return False
    ca, cb = char_class(a), char_class(b)
    if ca == "punct" or cb == "punct":
        return False
    if ca == "ascii" and cb == "ascii":
        return True
    if ca == "han" and cb == "han":
        return False
    # One side Han, the other ASCII — test the ASCII side. Never call isalnum()
    # on the Han side: "放".isalnum() is True in Python, which would silently
    # reintroduce spaces between Chinese characters.
    other = b if ca == "han" else a
    return other.isalnum() or other in "([{)]}"


def join_lines(lines):
    """Join soft-wrapped lines back into a single paragraph."""
    out = ""
    for line in lines:
        if not out:
            out = line
            continue
        out += (" " + line) if needs_space(out[-1], line[0]) else line
    return out


# Cases that have actually gone wrong at least once. selftest.py runs these.
CASES = [
    # (left char, right char, expect space, why)
    ("算", "放", False, "汉字 + 汉字 —— \"放\".isalnum() is True, the classic trap"),
    ("的", "影", False, "汉字 + 汉字"),
    ("代", '"', False, "汉字 + ASCII 直引号当中文引号用"),
    ("代", "“", False, "汉字 + 中文弯引号 (U+201C, 不在 CJK 块里)"),
    ("向", "[", True, "汉字 + 引用标记 [[cite:…]]"),
    ("向", "(", True, "汉字 + 西文括号"),
    ("的", "G", True, "汉字 + Latin 字母 (盘古之白)"),
    ("5", "年", True, "数字 + 汉字"),
    ("。", "云", False, "中文句号 + 汉字"),
    ("，", "数", False, "中文逗号 + 汉字"),
    ("—", "A", False, "破折号 (U+2014) 两侧不补"),
    ("…", "的", False, "省略号 (U+2026) 两侧不补"),
    ("g", "a", True, "Latin + Latin"),
    (")", "的", True, "引用括号收尾 + 汉字，同样按盘古之白留白"),
    ('"', "如", False, "ASCII 直引号 + 汉字（引号是中文引号的替身，不留白）"),
]


def check_cases():
    """Return a list of failure descriptions (empty means all good)."""
    bad = []
    for a, b, expect, why in CASES:
        got = needs_space(a, b)
        if got != expect:
            bad.append("{!r} + {!r}: expected space={} got {}  ({})"
                       .format(a, b, expect, got, why))
    return bad
