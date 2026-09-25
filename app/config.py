"""Paths and user-adjustable settings (config.json overrides DEFAULTS)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
VOCAB_DIR = CONTENT_DIR / "vocab"
BOOKS_DIR = CONTENT_DIR / "books"
VERBS_DIR = CONTENT_DIR / "verbs"
VOICES_DIR = ROOT / "voices"
PROFILES_DIR = Path(os.environ.get("GTUTOR_PROFILES") or ROOT / "data" / "profiles")  # tests use their own folder
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    "warmup_start": 10,          # words in the very first warm-up
    "warmup_max": 200,           # words per warm-up after about a year
    "warmup_growth": 0.52,       # extra words per day practised (10 -> 200 in ~365 days)
    "new_word_share": 0.25,      # part of the day's first warm-up that is new words
    "min_new_words": 3,          # always at least this many new words per day (until the bank runs out)
    "bank_shares": {"daily": 0.6, "stem": 0.25, "admin": 0.15},  # mix of new words per word list
    "units_per_day": 1,          # book paragraphs per day before asking "another one?"
    "speak_chance": 0.25,        # how often a word must be said into the microphone
    # Exercises for looking back (0 = never): read out loud, translate either way, listen and type a sentence,
    # shadow (hear a sentence, say it straight after).
    "reading_tasks": {"read_aloud": 1, "de2en": 1, "en2de": 1, "dictation": 1, "shadow": 1},
    "shadow_sentences": 5,       # sentences in a row when shadowing
    "look_back_sentences": 3,    # sentences in a row to translate when looking back at a paragraph
    "paragraph_reviews_per_session": 6,  # most earlier paragraphs to look back at in one session (oldest first)
    "verbs_per_day": 2,          # new irregular verbs (past + perfect) from the books, in the first warm-up
    "reading_words_per_day": 16,  # key words of read paragraphs added to the day's first warm-up (new or known)
    "genders_per_day": 8,        # new der/die/das cards per day (nouns already started), plus the due ones
    "grammar_per_day": 6,        # grammar questions from real sentences in the day's first warm-up
    # Some warm-up questions about words already met use the word's example sentence instead:
    # fill the gap, or listen and type the sentence (shares of those questions; 0 = never).
    "sentence_tasks": {"gap": 0.2, "dictation": 0.1},
    "speech_check": True,        # check with offline speech recognition that words were really said
    # Find the other kids on the same Wi-Fi: see who's online, get "… just finished a warm-up" news,
    # challenge each other to a duel. It sends the kid's name and results to every computer on the Wi-Fi, so:
    # "ask" = each kid is asked once (and can change it in menu 8); true = always on; false = always off
    # (nothing is sent or received; typing the host's address for a duel still works).
    "share_on_wifi": "ask",
    "word_record_seconds": 3,
    "voice": "de_DE-thorsten-medium",
    "word_speed": 1.15,          # >1 is slower; words are read slowly for learners
    "text_speed": 1.0,
    "input_device": None,        # sounddevice device index/name, None = system default
    "output_device": None,
    "sound_effects": True,       # retro sounds for right / wrong answers and for pressing Enter too fast
}


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULTS))
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open(encoding="utf-8") as f:
            user = json.load(f)
        settings.update({k: v for k, v in user.items() if not k.startswith("_")})
    return settings
