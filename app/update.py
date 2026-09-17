"""`gtutor update`: download the latest app, words and books from GitHub.

Progress in data/ is not tracked by git, so updating never touches it. Local edits to
tracked files (e.g. config.json) are stashed and re-applied around the pull.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys

from .config import ROOT, VOICES_DIR, load_settings
from .content import load_content
from .ui import console


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def _file_hash(name: str) -> str:
    path = ROOT / name
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def run_update() -> int:
    if not shutil.which("git") or not (ROOT / ".git").exists():
        console.print("[warn]This copy wasn't installed with git, so it can't update itself.[/]\n"
                      "Download the new ZIP from GitHub, unzip it over this folder, and keep your data/ folder.")
        return 1

    before = _git("rev-parse", "HEAD").stdout.strip()
    requirements_before = _file_hash("requirements.txt")
    with console.status("Checking GitHub for updates…"):
        pull = _git("pull", "--ff-only", "--autostash")
    if pull.returncode != 0:
        console.print("[red]Update failed.[/] Git said:\n" + (pull.stderr or pull.stdout).strip())
        console.print("[hint]Your progress is safe. Ask a parent to run 'git status' in this folder.[/]")
        return 1

    after = _git("rev-parse", "HEAD").stdout.strip()
    if before == after:
        console.print("[green]Already up to date.[/]")
        return 0

    changes = _git("log", "--format=  • %s", f"{before}..{after}").stdout.rstrip()
    console.print(f"[green]Updated![/] What's new:\n{changes}")

    if _file_hash("requirements.txt") != requirements_before:
        console.print("Installing new libraries…")
        pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=ROOT)
        if pip.returncode != 0:
            console.print("[red]Installing libraries failed.[/] Run setup.bat (or ./setup.sh) to repair.")
            return 1

    voice = load_settings()["voice"]
    if not (VOICES_DIR / f"{voice}.onnx").exists():
        console.print("Downloading the German voice…")
        subprocess.run([sys.executable, str(ROOT / "tools" / "download_voice.py"), voice], cwd=ROOT)

    content = load_content()
    console.print(f"[hint]{len(content.words)} words and {len(content.books)} books ready.[/]")
    return 0
