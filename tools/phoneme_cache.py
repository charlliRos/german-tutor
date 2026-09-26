"""Prepare the pronunciations of all the German the app speaks: python tools/phoneme_cache.py

Run it on a computer where the Piper voice works normally (espeak isn't blocked), after adding or changing
content. It writes content/phonemes_de.json.gz, which lets the voice work on computers where Windows' Smart
App Control blocks Piper's pronunciation helper (app/phonemes.py). Only new sentences are worked out again.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import VOICES_DIR, load_settings  # noqa: E402
from app.content import load_content  # noqa: E402
from app.exams import load_exams  # noqa: E402
from app.phonemes import CACHE_FILE, WORD, PhonemeCache, speech_texts, split  # noqa: E402


def main() -> int:
    from piper import PiperVoice
    voice = PiperVoice.load(VOICES_DIR / f"{load_settings()['voice']}.onnx")
    old = PhonemeCache.load() or PhonemeCache({}, {})
    texts = speech_texts(load_content(), load_exams()[0])
    sentences, words = {}, {}
    for text in texts:
        for s in split(text):
            if s in sentences:
                continue
            sentences[s] = old.sentences.get(s) or "".join(c for part in voice.phonemize(s) for c in part)
            for w in WORD.findall(s):
                w = w.lower()
                if w not in words:
                    words[w] = old.words.get(w) or "".join(c for part in voice.phonemize(w) for c in part).rstrip(".")
    data = json.dumps({"espeak": "de", "sentences": sentences, "words": words}, ensure_ascii=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8")
    CACHE_FILE.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    print(f"{len(sentences):,} sentences, {len(words):,} words -> {CACHE_FILE.name} ({CACHE_FILE.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
