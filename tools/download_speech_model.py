"""Download the offline German speech recognizer (Vosk small model, ~45 MB) into voices/ (one time).

It lets the app check that a word or text was really said out loud. Usage: python tools/download_speech_model.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import VOICES_DIR  # noqa: E402
from app.listen import MODEL_DIR, MODEL_NAME  # noqa: E402
from tools.download_voice import download  # noqa: E402

URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


def main() -> int:
    if MODEL_DIR.exists():
        print(f"  {MODEL_NAME}: already there")
        return 0
    VOICES_DIR.mkdir(exist_ok=True)
    archive = VOICES_DIR / f"{MODEL_NAME}.zip"
    download(URL, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(VOICES_DIR)
    archive.unlink()
    print(f"  {MODEL_NAME}: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
