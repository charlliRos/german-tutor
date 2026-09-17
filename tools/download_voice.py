"""Download the offline German Piper voice into voices/ (one time, ~63 MB).

Usage: python tools/download_voice.py [voice-name]   (default: the voice in config)
Browse other voices: https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import VOICES_DIR, load_settings  # noqa: E402

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/{speaker}/{quality}/{name}{ext}?download=true"


def download(url: str, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done = shown = 0
        while chunk := response.read(1 << 16):
            out.write(chunk)
            done += len(chunk)
            if total and done * 100 // total >= shown + 10:  # every 10%
                shown = done * 100 // total
                print(f"\r  {target.name}: {shown}%", end="", flush=True)
    tmp.replace(target)
    print(f"\r  {target.name}: done      ")


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else load_settings()["voice"]
    try:
        _, speaker, quality = name.split("-")  # de_DE-thorsten-medium
    except ValueError:
        print(f"Voice names look like de_DE-thorsten-medium, got {name!r}")
        return 1
    VOICES_DIR.mkdir(exist_ok=True)
    for ext in (".onnx.json", ".onnx"):
        target = VOICES_DIR / f"{name}{ext}"
        if target.exists() and target.stat().st_size > 0:
            print(f"  {target.name}: already there")
            continue
        download(BASE.format(speaker=speaker, quality=quality, name=name, ext=ext), target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
