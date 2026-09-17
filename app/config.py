"""Paths and user-adjustable settings (config.json overrides DEFAULTS)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
VOCAB_DIR = CONTENT_DIR / "vocab"
BOOKS_DIR = CONTENT_DIR / "books"
VOICES_DIR = ROOT / "voices"
PROFILES_DIR = ROOT / "data" / "profiles"
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    "warmup_words": 20,          # max words per warm-up (reviews + new)
    "new_words_per_day": 8,      # new words introduced per day
    "stem_share": 0.3,           # fraction of new words taken from the STEM bank
    "units_per_day": 1,          # book paragraphs per day before asking "another one?"
    "speak_chance": 0.25,        # how often a word must be said into the microphone
    "reading_tasks": {"read_aloud": 1, "de2en": 1, "en2de": 1},  # relative weights
    "word_record_seconds": 3,
    "voice": "de_DE-thorsten-medium",
    "word_speed": 1.15,          # >1 is slower; words are read slowly for learners
    "text_speed": 1.0,
    "input_device": None,        # sounddevice device index/name, None = system default
    "output_device": None,
}


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULTS))
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open(encoding="utf-8") as f:
            user = json.load(f)
        settings.update({k: v for k, v in user.items() if not k.startswith("_")})
    return settings
