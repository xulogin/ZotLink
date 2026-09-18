# -*- coding: utf-8 -*-
"""Scaffold a new ZotLink manuscript project.

Creates:
  <dir>/content/<name>.md      markdown skeleton with cite + bibliography markers
  <dir>/data/references.bib    empty BibTeX file
  <dir>/reports/  <dir>/output/
  <dir>/zotlink.json           per-project config (only written with --data-dir)
  <dir>/README.md              how to run this project

Run:
  python scripts/new_project.py <dir> [--title "标题"] [--name introduction]
                                      [--data-dir "D:/Zotero"] [--force]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_ROOT / "template"


def arg(flag, argv, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    for a in argv:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def main():
    zot_env.force_utf8()
    argv = sys.argv[1:]
    positional = []
    skip_next = False
    for i, a in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if a.startswith("--"):
            if "=" not in a and a not in ("--force",):
                skip_next = True
            continue
        positional.append(a)

    if not positional:
        sys.exit(__doc__)

    root = Path(positional[0]).expanduser().resolve()
    name = arg("--name", argv, "manuscript")
    title = arg("--title", argv, name)
    data_dir = arg("--data-dir", argv)
    force = "--force" in argv

    if root.exists() and any(root.iterdir()) and not force:
        sys.exit("FATAL: {} already exists and is not empty (use --force)".format(root))

    for sub in ("content", "data", "reports", "output"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    md = root / "content" / "{}.md".format(name)
    if not md.exists() or force:
        md.write_text(
            (TEMPLATE / "content" / "example.md").read_text(encoding="utf-8")
            .replace("{{TITLE}}", title),
            encoding="utf-8")

    bib = root / "data" / "references.bib"
    if not bib.exists() or force:
        bib.write_text("% references.bib — add your BibTeX entries here.\n"
                       "% Key style: lastname + YYYY + first meaningful word,\n"
                       "% e.g. calders2020terrestrial. Same surname? prefix the\n"
                       "% given name's initial: liuc2021 / liuj2021.\n",
                       encoding="utf-8")

    readme = root / "README.md"
    if not readme.exists() or force:
        readme.write_text(
            (TEMPLATE / "README.md").read_text(encoding="utf-8")
            .replace("{{TITLE}}", title).replace("{{NAME}}", name),
            encoding="utf-8")

    if data_dir:
        (root / zot_env.CONFIG_NAME).write_text(
            json.dumps({"zotero_data_dir": data_dir}, indent=2), encoding="utf-8")

    print("created project at {}".format(root))
    print("  content/{}.md".format(name))
    print("  data/references.bib")
    print("\nnext:")
    print("  1. add BibTeX entries to data/references.bib")
    print("  2. write content/{}.md, cite with [[cite:key]]".format(name))
    print('  3. python "{}/scripts/run.py" --project "{}"'.format(SKILL_ROOT.as_posix(), root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
