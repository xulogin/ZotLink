# -*- coding: utf-8 -*-
"""Match every CSL entry in data/references.json to a real item in the local
Zotero library, by reading zotero.sqlite directly (read-only, WAL-safe).

Why: Zotero's Word plugin resolves a citation field by URI first. If we bake
the *real* itemKey URI into the docx, Refresh is instant and silent. If we
don't, Zotero falls back to DOI then fuzzy-title matching and starts popping
up "select the right item" dialogs.

Writes:
  reports/zot_match_report.md      human-readable, per citekey + strategy
  reports/zot_match_index.json     citekey -> {itemKey, itemID, uri, strategy}
  reports/references_missing.bib   only the entries not found (import these)

Run:  python scripts/zot_match.py [--project DIR]
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

PROJ, _ = zot_env.open_project()
PROJ.ensure_dirs()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def norm_doi(s):
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    return s or None


def norm_title(s):
    """Aggressive normalisation — keep only [a-z0-9] so '3-D' == '3D' == '3 D'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _pick_best_duplicate(cands):
    """When several Zotero items are duplicates of the same paper, prefer the
    one with a DOI populated; tiebreak by lowest itemID (oldest import)."""
    with_doi = [c for c in cands if c.get("doi")]
    pool = with_doi or cands
    return sorted(pool, key=lambda c: c["itemID"])[0]


def _all_same_paper(cands):
    """True if every candidate has the same normalised title (i.e. duplicates)."""
    titles = set(norm_title(c["title"]) for c in cands if c["title"])
    return len(titles) <= 1 and bool(titles)


def first_significant_word(title):
    stop = {"a", "an", "the", "and", "or", "of", "on", "in", "to", "for",
            "with", "using", "from", "by", "at", "as", "is", "are"}
    for w in re.split(r"[^a-z0-9]+", (title or "").lower()):
        if w and w not in stop and not w.isdigit() and len(w) > 2:
            return w
    return ""


# ---------------------------------------------------------------------------
# Load CSL entries
# ---------------------------------------------------------------------------
if not PROJ.csl_json.exists():
    sys.exit("FATAL: {} not found — run pandoc (or scripts/run.py) first"
             .format(PROJ.csl_json))

with open(PROJ.csl_json, "r", encoding="utf-8") as f:
    csl_list = json.load(f)

print("[csl] loaded {} entries from {}".format(len(csl_list), PROJ.csl_json))


# ---------------------------------------------------------------------------
# Load Zotero library
# ---------------------------------------------------------------------------
DB = PROJ.db()
conn = zot_env.connect_ro(DB)
cur = conn.cursor()
URI_PREFIX = zot_env.library_uri_prefix(conn, PROJ.cfg)
print("[zot] db  {}".format(DB))
print("[zot] uri {}<itemKey>".format(URI_PREFIX))

# itemData is a thin EAV table, hence the scalar subqueries.
cur.execute("""
    SELECT
      i.itemID,
      i.key                                                                     AS itemKey,
      (SELECT v.value FROM itemDataValues v JOIN itemData d ON d.valueID = v.valueID
        JOIN fields f ON d.fieldID = f.fieldID WHERE d.itemID = i.itemID AND f.fieldName = 'title') AS title,
      (SELECT v.value FROM itemDataValues v JOIN itemData d ON d.valueID = v.valueID
        JOIN fields f ON d.fieldID = f.fieldID WHERE d.itemID = i.itemID AND f.fieldName = 'DOI')   AS doi,
      (SELECT v.value FROM itemDataValues v JOIN itemData d ON d.valueID = v.valueID
        JOIN fields f ON d.fieldID = f.fieldID WHERE d.itemID = i.itemID AND f.fieldName = 'date')  AS date,
      (SELECT c.lastName FROM creators c JOIN itemCreators ic ON ic.creatorID = c.creatorID
        WHERE ic.itemID = i.itemID ORDER BY ic.orderIndex ASC LIMIT 1)         AS first_author
    FROM items i
    WHERE i.itemTypeID NOT IN
      (SELECT itemTypeID FROM itemTypes WHERE typeName IN ('attachment','note'))
      AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
""")

lib_rows = cur.fetchall()
print("[zot] loaded {} library items (excl. attachments/notes/trashed)".format(len(lib_rows)))

by_doi = {}
by_norm_title = {}
by_author_year = {}

for row in lib_rows:
    itemID, itemKey, title, doi, date, author = row
    rec = {"itemID": itemID, "itemKey": itemKey, "title": title,
           "doi": doi, "date": date, "author": author}
    d = norm_doi(doi)
    if d:
        by_doi.setdefault(d, []).append(rec)
    nt = norm_title(title)
    if nt:
        by_norm_title.setdefault(nt, []).append(rec)
    year = ""
    if date:
        m = re.search(r"(19|20)\d{2}", date)
        if m:
            year = m.group(0)
    if author and year:
        by_author_year.setdefault((author.lower(), year), []).append(rec)

print("[idx] {} DOIs, {} unique titles, {} (author,year) pairs"
      .format(len(by_doi), len(by_norm_title), len(by_author_year)))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def csl_year(entry):
    try:
        return str(entry["issued"]["date-parts"][0][0])
    except Exception:
        return ""


def csl_first_author_last(entry):
    authors = entry.get("author") or entry.get("editor") or []
    if not authors:
        return ""
    return (authors[0].get("family") or authors[0].get("literal") or "").lower()


report_lines = ["# Zotero match report\n",
                "- references.json: {} entries".format(len(csl_list)),
                "- Zotero library items scanned: {}".format(len(lib_rows)),
                "- library URI prefix: `{}`\n".format(URI_PREFIX),
                "| # | citekey | strategy | itemKey | itemID | matched title |",
                "|---|---|---|---|---|---|"]

index = {}
ambiguous_keys = set()
hits = ambig = miss = 0

for i, entry in enumerate(csl_list, 1):
    key = entry["id"]
    csl_doi = norm_doi(entry.get("DOI"))
    csl_title_norm = norm_title(entry.get("title"))
    csl_y = csl_year(entry)
    csl_au = csl_first_author_last(entry)

    matched = None
    strategy = None
    candidates = []

    # 1. DOI exact (duplicates collapsed)
    if csl_doi and csl_doi in by_doi:
        cands = by_doi[csl_doi]
        if len(cands) == 1:
            matched, strategy = cands[0], "doi"
        elif _all_same_paper(cands):
            matched, strategy = _pick_best_duplicate(cands), "doi+dedup({})".format(len(cands))
        else:
            candidates = cands
            strategy = "doi-ambiguous"

    # 2. Normalised title exact (duplicates collapsed)
    if not matched and csl_title_norm and csl_title_norm in by_norm_title:
        cands = by_norm_title[csl_title_norm]
        if len(cands) == 1:
            matched, strategy = cands[0], "title"
        elif _all_same_paper(cands):
            matched, strategy = _pick_best_duplicate(cands), "title+dedup({})".format(len(cands))
        else:
            year_match = [c for c in cands if c.get("date") and csl_y and csl_y in c["date"]]
            if len(year_match) == 1:
                matched, strategy = year_match[0], "title+year"
            else:
                candidates = cands
                strategy = "title-ambiguous"

    # 3. Author lastname + year (+ first significant title word)
    if not matched and csl_au and csl_y:
        cands = by_author_year.get((csl_au, csl_y), [])
        fsw = first_significant_word(entry.get("title", ""))
        if fsw:
            filtered = [c for c in cands if fsw in (norm_title(c["title"]) or "")]
            if len(filtered) == 1:
                matched, strategy = filtered[0], "author+year+word"
            elif filtered and _all_same_paper(filtered):
                matched, strategy = _pick_best_duplicate(filtered), "author+year+dedup({})".format(len(filtered))
            elif len(filtered) > 1:
                candidates = filtered
                strategy = "author-year-ambiguous"
        elif len(cands) == 1:
            matched, strategy = cands[0], "author+year"
        elif cands and _all_same_paper(cands):
            matched, strategy = _pick_best_duplicate(cands), "author+year+dedup({})".format(len(cands))
        elif len(cands) > 1:
            candidates = cands
            strategy = "author-year-ambiguous"

    # 4. Loose fallback: title substring — BOTH sides must be long enough, or a
    # Chinese-titled item that normalises to a handful of latin letters
    # ("lidar") would match every long English title.
    if not matched and csl_title_norm and len(csl_title_norm) > 15:
        fuzzy = []
        for nt, recs in by_norm_title.items():
            if len(nt) < 15:
                continue
            if csl_title_norm in nt or nt in csl_title_norm:
                fuzzy.extend(recs)
        if len(fuzzy) == 1:
            matched, strategy = fuzzy[0], "title-fuzzy"
        elif fuzzy and _all_same_paper(fuzzy):
            matched, strategy = _pick_best_duplicate(fuzzy), "title-fuzzy+dedup({})".format(len(fuzzy))
        elif len(fuzzy) > 1:
            candidates = fuzzy[:5]
            strategy = "title-fuzzy-ambiguous"

    if matched:
        hits += 1
        title_short = (matched["title"] or "?")[:80].replace("|", "\\|")
        report_lines.append(
            "| {} | `{}` | {} | `{}` | {} | {} |".format(
                i, key, strategy, matched["itemKey"], matched["itemID"], title_short))
        index[key] = {
            "itemKey": matched["itemKey"],
            "itemID": matched["itemID"],
            "uri": URI_PREFIX + matched["itemKey"],
            "strategy": strategy,
        }
    else:
        if candidates:
            ambig += 1
            ambiguous_keys.add(key)
            cand_summary = "; ".join(
                "{} ({})".format(c["itemKey"], (c["title"] or "?")[:40]) for c in candidates[:3])
            report_lines.append(
                "| {} | `{}` | **AMBIG ({})** |  |  | candidates: {} |".format(
                    i, key, strategy, cand_summary))
        else:
            miss += 1
            report_lines.append(
                "| {} | `{}` | **MISS** |  |  | DOI=`{}` title=`{}` |".format(
                    i, key, csl_doi, (entry.get("title") or "")[:60]))

# ---------------------------------------------------------------------------
# Collision detection: if two citekeys claim the same itemKey, only the
# strongest strategy keeps it; the weaker one goes back to "missing".
# ---------------------------------------------------------------------------
STRATEGY_RANK = {
    "doi": 0, "doi+dedup": 0,
    "title+year": 1, "title": 2, "title+dedup": 2,
    "author+year+word": 3, "author+year": 3, "author+year+dedup": 3,
    "title-fuzzy": 4, "title-fuzzy+dedup": 4,
}


def _rank(strat):
    return STRATEGY_RANK.get(strat.split("(")[0], 99)


by_itemkey = {}
for k, info in index.items():
    by_itemkey.setdefault(info["itemKey"], []).append(k)

collisions = dict((ik, ks) for ik, ks in by_itemkey.items() if len(ks) > 1)
if collisions:
    report_lines.append("\n## Collisions resolved")
    for ik, ks in collisions.items():
        ranked = sorted(ks, key=lambda k: _rank(index[k]["strategy"]))
        winner, losers = ranked[0], ranked[1:]
        report_lines.append(
            "- itemKey `{}`: kept `{}` ({}); unmatched: {}".format(
                ik, winner, index[winner]["strategy"], ", ".join(losers)))
        for loser in losers:
            del index[loser]
            hits -= 1
            miss += 1

# Insert (don't overwrite) — index 4 is the table's header row, and clobbering
# it leaves a markdown table with no header that renders as raw pipes.
report_lines.insert(4, "- **matched: {}  /  ambiguous: {}  /  miss: {}**\n".format(hits, ambig, miss))
PROJ.match_report.write_text("\n".join(report_lines), encoding="utf-8")
PROJ.match_index.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------------------------------------------------------------------------
# Emit a .bib holding only the unmatched entries — run.py POSTs this to
# Zotero's connector (or you drag it in by hand), then re-run.
# ---------------------------------------------------------------------------
# Ambiguous keys are deliberately excluded: the paper IS in the library, we
# just can't tell which duplicate to use. Re-importing would add a third copy.
missing_keys = set(e["id"] for e in csl_list) - set(index.keys()) - ambiguous_keys
if ambiguous_keys:
    print("note: {} ambiguous key(s) left out of references_missing.bib "
          "(already in the library — disambiguate in Zotero): {}"
          .format(len(ambiguous_keys), ", ".join(sorted(ambiguous_keys))))
if PROJ.missing_bib.exists():
    PROJ.missing_bib.unlink()
if missing_keys and PROJ.bib.exists():
    text = PROJ.bib.read_text(encoding="utf-8")
    wanted = []
    for m in re.finditer(r"(@\w+\{([^,]+),.*?\n\})\s*\n", text, flags=re.DOTALL):
        if m.group(2).strip() in missing_keys:
            wanted.append(m.group(1))
    header = ("% references_missing.bib — auto-generated by ZotLink.\n"
              "% Entries not found in the Zotero library on the last match run.\n"
              "% Import into Zotero (File → Import), then re-run the pipeline.\n\n")
    PROJ.missing_bib.write_text(header + "\n\n".join(wanted) + "\n", encoding="utf-8")
    print("missing-bib -> {}  ({} entries)".format(PROJ.missing_bib, len(wanted)))

print("\n=== SUMMARY ===  hits={}  ambig={}  miss={}".format(hits, ambig, miss))
print("report -> {}".format(PROJ.match_report))
print("index  -> {}".format(PROJ.match_index))

conn.close()
