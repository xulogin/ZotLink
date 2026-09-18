# -*- coding: utf-8 -*-
"""End-to-end self test.

Copies examples/demo into a temp directory, runs the full pipeline against
your real Zotero library, and verifies the resulting docx. Nothing is written
to your Zotero database (the cleaner is never invoked); the only side effect
is that the five demo references get imported into your library if they are
not there yet and Zotero is running.

Run:  python scripts/selftest.py [--keep]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zot_env  # noqa: E402

zot_env.force_utf8()

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
DEMO = SKILL_ROOT / "examples" / "demo"

results = []


def stage(name, argv):
    print("\n" + "-" * 60)
    print("  {}".format(name))
    print("-" * 60)
    sys.stdout.flush()   # keep the child's output under its own header
    r = subprocess.run([sys.executable] + argv, text=True)
    results.append((name, r.returncode == 0))
    return r.returncode == 0


def main():
    if not DEMO.is_dir():
        sys.exit("FATAL: {} missing — is the checkout complete?".format(DEMO))

    tmp = Path(tempfile.mkdtemp(prefix="zotlink-selftest-"))
    work = tmp / "demo"
    shutil.copytree(DEMO, work)
    print("workdir {}".format(work))

    stage("doctor", [str(HERE / "doctor.py"), "--project", str(work)])
    ok_run = stage("run (pandoc -> match -> scan -> build)",
                   [str(HERE / "run.py"), "--project", str(work), "--skip-dirty"])
    ok_verify = False
    if ok_run:
        ok_verify = stage("verify_docx", [str(HERE / "verify_docx.py"), "--project", str(work)])

    print("\n" + "=" * 60)
    for name, ok in results:
        print("  {}  {}".format("PASS" if ok else "FAIL", name))
    print("=" * 60)

    if "--keep" in sys.argv:
        print("workdir kept at {}".format(work))
    else:
        shutil.rmtree(tmp, ignore_errors=True)

    # doctor's connector warning is non-fatal, but it exits 0 anyway; the real
    # gate is that the pipeline ran and the docx verified.
    if ok_run and ok_verify:
        print("SELFTEST PASSED")
        return 0
    print("SELFTEST FAILED — see the output above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
