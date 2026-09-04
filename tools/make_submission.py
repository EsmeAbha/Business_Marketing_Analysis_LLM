"""Build the submission zip, and prove what is in it.

The first submission was marked down to 73 because the uploaded zip held
slide assets and a 52-line helper — no application source. Nothing about
that was a false claim; the wrong file was uploaded. So the packaging is a
script rather than a hand-assembled folder, and it ends by checking itself
against the assignment's own deliverable list.

`git archive` is the source of truth for what goes in: it ships exactly the
tracked files, which means .env, data/, the session key and every shop's
database cannot be included by accident. Hand-zipping a working directory is
how a secret gets submitted.

    python tools/make_submission.py

Writes dist/Lucida_Submission.zip and prints the audit.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "Lucida_Submission.zip"

# What the assignment asks to be in the package, and how to recognise it.
# Phrased as "some file matching this", because the check should survive a
# rename that keeps the deliverable.
REQUIRED = [
    ("Source code", lambda n: n.startswith("src/lucida/") and n.endswith(".py")),
    ("Supervisor", lambda n: n == "src/lucida/supervisor.py"),
    ("Agent definitions", lambda n: n.startswith("src/lucida/agents/")
     and n.endswith(".py")),
    ("Graph / state machine", lambda n: n == "src/lucida/graph.py"),
    ("Memory + RAG", lambda n: n.startswith("src/lucida/memory/")),
    ("Tools", lambda n: n.startswith("src/lucida/tools/")),
    ("Dashboard (UI)", lambda n: n.startswith("web/")),
    ("Tests", lambda n: n.startswith("tests/")),
    ("Entry point", lambda n: n == "serve.py"),
    ("README with setup", lambda n: n == "README.md"),
    ("Architecture diagram", lambda n: n.startswith("docs/architecture.")
     and n.rsplit(".", 1)[-1] in ("svg", "png")),
    ("Presentation slides", lambda n: n.endswith(".pptx")),
    ("Requirements", lambda n: n == "requirements.txt"),
]

# Anything matching these must never appear. A submission that leaks an owner
# database or an API key is a worse outcome than a late one.
FORBIDDEN = [
    (".env file", lambda n: n == ".env" or n.endswith("/.env")),
    ("session key", lambda n: n.endswith(".key")),
    ("owner database", lambda n: n.endswith(".db")),
    ("shop data", lambda n: n.startswith("data/shops/")),
    ("bytecode", lambda n: "__pycache__" in n or n.endswith(".pyc")),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    # --prefix so the zip opens into a named folder rather than spraying
    # files into whatever directory the marker unzips it in.
    git("archive", "--format=zip", "--prefix=Lucida/", "-o", str(OUT), "HEAD")
    return OUT


def audit(path: Path) -> int:
    with zipfile.ZipFile(path) as z:
        names = [n[len("Lucida/"):] for n in z.namelist()
                 if n.startswith("Lucida/") and not n.endswith("/")]

    print(f"\n{path.relative_to(ROOT)}  —  {len(names)} files, "
          f"{path.stat().st_size / 1_048_576:.1f} MB\n")

    failed = 0
    print("Required by the assignment:")
    for label, match in REQUIRED:
        hits = [n for n in names if match(n)]
        mark = "ok " if hits else "MISSING"
        if not hits:
            failed += 1
        detail = f"{len(hits)} file(s)" if hits else "nothing matched"
        print(f"  [{mark:^7}] {label:<24} {detail}")

    print("\nMust not be present:")
    for label, match in FORBIDDEN:
        hits = [n for n in names if match(n)]
        if hits:
            failed += 1
            print(f"  [ LEAK  ] {label:<24} {hits[:3]}")
        else:
            print(f"  [  ok   ] {label:<24} absent")

    py = [n for n in names if n.endswith(".py")]
    agents = [n for n in names if n.startswith("src/lucida/agents/")
              and n.endswith(".py")
              and Path(n).stem not in ("__init__", "base", "schemas")]
    print(f"\nContents: {len(py)} Python files, {len(agents)} specialist agents, "
          f"1 supervisor")
    print(f"Built from commit {git('rev-parse', '--short', 'HEAD')} "
          f"({git('rev-list', '--count', 'HEAD')} commits)")
    return failed


if __name__ == "__main__":
    if git("status", "--porcelain"):
        print("Working tree is dirty — commit first, or the zip will not "
              "match the repository it claims to be.\n", file=sys.stderr)
    problems = audit(build())
    print()
    if problems:
        print(f"{problems} problem(s) — do not submit this.")
        sys.exit(1)
    print("Package is complete. Nothing sensitive included.")
