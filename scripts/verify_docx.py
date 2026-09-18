# -*- coding: utf-8 -*-
"""Verify that a built docx really carries live Zotero fields.

"It ran without errors" is not the same as "Word will resolve it". This
opens the docx, pulls every ADDIN ZOTERO_ITEM / ZOTERO_BIBL field out of
word/document.xml and checks that:

  - every [[cite:...]] in the markdown became a CSL_CITATION field
  - every citationItem carries a `uris` entry
  - every URI's itemKey matches reports/zot_match_index.json
  - every URI's prefix matches this machine's Zotero library identity
  - there is exactly one CSL_BIBLIOGRAPHY field per [[bibliography]] marker

Run:  python scripts/verify_docx.py [--project DIR] [output/foo.docx]
Exit: 0 all good, 1 something would fail on Refresh.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

PROJ, ARGS = zot_env.open_project()

if ARGS:
    docx_path = Path(ARGS[0])
    if not docx_path.is_absolute():
        docx_path = PROJ.root / docx_path
else:
    cands = sorted(PROJ.output.glob("*.docx"))
    if not cands:
        sys.exit("FATAL: no docx in {}".format(PROJ.output))
    docx_path = max(cands, key=lambda p: p.stat().st_mtime)

if not docx_path.exists():
    sys.exit("FATAL: {} not found".format(docx_path))

index = json.loads(PROJ.match_index.read_text(encoding="utf-8"))
known_keys = set(v["itemKey"] for v in index.values())
known_uris = set(v["uri"] for v in index.values())

with zipfile.ZipFile(docx_path) as z:
    xml = z.read("word/document.xml").decode("utf-8")

# Word may split instrText across runs; concatenate the instrText contents in
# document order, then slice out the ADDIN payloads.
instr_chunks = re.findall(r"<w:instrText[^>]*>(.*?)</w:instrText>", xml, flags=re.DOTALL)
blob = "".join(instr_chunks)


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))


citations = [_unescape(m) for m in
             re.findall(r"ADDIN ZOTERO_ITEM CSL_CITATION (\{.*?\}) RND ", blob, flags=re.DOTALL)]
bibls = re.findall(r"ADDIN ZOTERO_BIBL .*? CSL_BIBLIOGRAPHY", blob, flags=re.DOTALL)

# Expected counts, straight from the markdown source
md_candidates = sorted(PROJ.content.glob("*.md"))
md = None
for c in md_candidates:
    if c.stem == docx_path.stem:
        md = c
        break
md = md or (md_candidates[0] if md_candidates else None)
expect_cites = expect_bibl = None
if md:
    text = "\n".join(ln for ln in md.read_text(encoding="utf-8").split("\n")
                     if not ln.strip().startswith("%%"))
    expect_cites = len(re.findall(r"\[\[cite:[^\]]+\]\]", text))
    expect_bibl = len(re.findall(r"^\[\[bibliography(?::[^\]]*)?\]\]\s*$",
                                 text, flags=re.MULTILINE))

problems = []
print("docx      {}".format(docx_path))
print("markdown  {}".format(md if md else "(not found)"))
print("citations {} field(s)".format(len(citations)))
print("bibliography {} field(s)".format(len(bibls)))

if expect_cites is not None and len(citations) != expect_cites:
    problems.append("markdown has {} [[cite:]] marker(s) but the docx has {} citation field(s)"
                    .format(expect_cites, len(citations)))
if expect_bibl is not None and len(bibls) != expect_bibl:
    problems.append("markdown has {} [[bibliography]] marker(s) but the docx has {}"
                    .format(expect_bibl, len(bibls)))

uri_count = 0
for n, raw in enumerate(citations, 1):
    try:
        payload = json.loads(raw)
    except ValueError as e:
        problems.append("citation #{}: payload is not valid JSON ({})".format(n, e))
        continue
    items = payload.get("citationItems") or []
    if not items:
        problems.append("citation #{}: no citationItems".format(n))
    for it in items:
        uris = it.get("uris") or []
        if not uris:
            problems.append("citation #{}: item has no uris — Word will fall back to "
                            "DOI/title matching and may prompt".format(n))
            continue
        for u in uris:
            uri_count += 1
            if u not in known_uris:
                problems.append("citation #{}: uri {} is not in zot_match_index.json".format(n, u))
            elif u.rsplit("/", 1)[-1] not in known_keys:
                problems.append("citation #{}: itemKey {} unknown".format(n, u))
        if not it.get("itemData"):
            problems.append("citation #{}: item has no itemData (Zotero needs it to "
                            "render before the library lookup)".format(n))

print("uris      {} reference(s), all resolvable: {}".format(uri_count, not problems))

if problems:
    print("\nPROBLEMS:")
    for p in problems:
        print("  - {}".format(p))
    sys.exit(1)

print("\nOK — open it in Word and hit Zotero -> Refresh.")
sys.exit(0)
