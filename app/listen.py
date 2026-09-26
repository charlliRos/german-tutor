"""Did the kid really say it? Offline speech recognition (Vosk, small German model) on a recording.

It only checks that the right words were said, generously: a learner's accent is fine, silence or a
different sentence is not. Without the model (not downloaded, or vosk missing) nothing is checked.
"""
from __future__ import annotations

import difflib
import json
import os

import numpy as np

from .answers import normalize
from .config import VOICES_DIR

MODEL_NAME = "vosk-model-small-de-0.15"
MODEL_DIR = VOICES_DIR / MODEL_NAME
RATE = 16000
WORD_MATCH = 0.7    # a heard word this close to an expected one counts (Regenschirm ~ regenschirme)
TEXT_SHARE = 0.4    # a sentence or paragraph counts when this share of its words was heard
# Small words don't show that the right thing was said.
_SMALL = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "und", "oder",
          "ich", "du", "er", "sie", "es", "wir", "ihr", "sich", "zu", "in", "an", "auf", "mit", "von", "ist"}


class Listener:
    def __init__(self) -> None:
        import vosk
        vosk.SetLogLevel(-1)
        self._vosk = vosk
        self._model = vosk.Model(str(MODEL_DIR))

    def transcribe(self, audio: np.ndarray, rate: int) -> str:
        """What the recognizer heard, lowercase ('' for silence)."""
        from .audio import _resample
        pcm = (np.clip(_resample(audio, rate, RATE), -1, 1) * 32767).astype(np.int16).tobytes()
        rec = self._vosk.KaldiRecognizer(self._model, RATE)
        rec.AcceptWaveform(pcm)
        return json.loads(rec.FinalResult()).get("text", "").strip()


def load() -> tuple[Listener | None, str]:
    """(listener, problem). The problem is '' when it works, or says why there's no speech check. If the offline
    checker can't run (not downloaded, or Windows blocks its unsigned file), Windows' own German speech
    recognition is used when it's installed (app/sysrecognize.py)."""
    if not MODEL_DIR.exists():
        problem = "The speech checker isn't downloaded yet. Run: gtutor update"
    else:
        try:
            return Listener(), ""
        except Exception as exc:  # vosk not installed, a damaged model, or blocked by Windows
            text = str(exc).lower()
            problem = ("Windows blocked the speech checker (Smart App Control or a school's app policy)."
                       if "application control" in text or "blocked" in text else
                       f"The speech checker couldn't start ({exc}). Run: gtutor update")
    if os.name == "nt":
        try:
            from .sysrecognize import WindowsRecognizer
            return WindowsRecognizer("de"), ""
        except Exception:
            problem += (" Speaking turns aren't checked here; for Windows' own German speech check, add the German "
                        "speech pack (Settings → Time & language → Language → Deutsch → Speech). Everything else works.")
    return None, problem


def _close(word: str, heard: list[str]) -> bool:
    # Compound words are sometimes heard as two (Regen schirm): also try neighbours joined.
    options = heard + [a + b for a, b in zip(heard, heard[1:])]
    return any(word == h or difflib.SequenceMatcher(a=word, b=h).ratio() >= WORD_MATCH for h in options)


def said_it(heard: str, expected: str) -> bool:
    """Generous: one word needs its main word heard; a longer text needs TEXT_SHARE of its words."""
    got = normalize(heard).split()
    if not got:
        return False
    words = normalize(expected).split()
    main = [w for w in words if w not in _SMALL] or words
    if not main:
        return True
    hits = sum(_close(w, got) for w in main)
    return hits >= (1 if len(main) <= 2 else max(1, round(len(main) * TEXT_SHARE)))
