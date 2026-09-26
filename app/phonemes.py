"""Prepared pronunciations, so the offline voice works where Windows blocks its pronunciation helper.

The Piper voice has two halves: espeak turns German text into pronunciation codes (phonemes), then the neural
voice turns codes into sound. The second half runs on onnxruntime, which Microsoft signs, so Smart App Control
allows it; the first half is an unsigned file (espeakbridge) that it may block. This file holds the codes for
all the German the app speaks, made on a computer where espeak works (tools/phoneme_cache.py), so the voice
works everywhere. Text that isn't in it is put together from its words' codes.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from .config import CONTENT_DIR

CACHE_FILE = CONTENT_DIR / "phonemes_de.json.gz"
_QUOTES = str.maketrans({c: " " for c in "„“”\"»«‹›‚‘’"})
WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:['’][a-z]+)?")


def key(text: str) -> str:
    """Texts that sound the same share a key: no quotes, single spaces."""
    from .audio import clean_for_speech
    return " ".join(clean_for_speech(text).translate(_QUOTES).split())


def split(text: str) -> list[str]:
    from .content import sentences
    return [key(s) for s in sentences(key(text)) if key(s)] or ([key(text)] if key(text) else [])


class PhonemeCache:
    def __init__(self, sentences: dict[str, str], words: dict[str, str]) -> None:
        self.sentences, self.words = sentences, words

    @classmethod
    def load(cls, path: Path = CACHE_FILE) -> "PhonemeCache | None":
        try:
            data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        except (OSError, ValueError):
            return None
        return cls(data.get("sentences", {}), data.get("words", {}))

    def sentence(self, sentence: str) -> str:
        """The codes for one sentence: prepared, or put together from its words ('' if none are known)."""
        if sentence in self.sentences:
            return self.sentences[sentence]
        parts = [self.word(w) for w in WORD.findall(sentence)]
        known = [p for p in parts if p]
        if not known:
            return ""
        end = "?" if sentence.rstrip().endswith("?") else "!" if sentence.rstrip().endswith("!") else "."
        return " ".join(known) + end

    def word(self, word: str, depth: int = 0) -> str:
        """A word's codes; an unknown compound is put together from two known parts (Blumen + laden)."""
        w = word.lower()
        if w in self.words:
            return self.words[w]
        if depth < 2 and len(w) >= 7:
            for i in range(len(w) - 3, 2, -1):  # the longest known ending first: it carries the meaning
                head, tail = w[:i], w[i:]
                tail_codes = self.words.get(tail) or (self.words.get(tail[1:]) if head.endswith(("s", "n")) else None)
                if tail_codes and (head_codes := self.word(head, depth + 1)):
                    return head_codes + tail_codes.replace("ˈ", "ˌ", 1)
        return ""

    def phonemize(self, text: str) -> list[list[str]]:
        """A stand-in for PiperVoice.phonemize: codes per sentence, as lists of single characters."""
        return [list(codes) for codes in (self.sentence(s) for s in split(text)) if codes]

    def coverage(self, texts) -> float:
        wanted = {s for t in texts for s in split(t)}
        return sum(1 for s in wanted if s in self.sentences) / len(wanted) if wanted else 1.0


def speech_texts(content, exams=()) -> list[str]:
    """Every German text the app can speak: words, examples, book sentences, paragraphs, verb forms, exam
    recordings, partner lines and model answers."""
    texts = ["Hallo", "Hallo! Das ist ein Test."]
    for w in content.words.values():
        texts += [w.de, w.example_de, w.story_de.strip("… ")]
    for book in content.books:
        for unit in book.units:
            if unit.kind == "text":
                texts.append(unit.de)
                texts += [de for de, _ in unit.sentence_pairs]
    for verb in content.verbs.values():
        texts.append(f"{verb.inf}. {verb.past}. {verb.perfect}.")
    for exam in exams:
        for part in exam.parts:
            for t in part.texts:
                texts += [t.de, *(line["de"] for line in t.lines)]
            for task in part.tasks:
                texts += [task.partner_de, task.model_de]
            texts.append(part.model_de)
    return [t for t in texts if t and t.strip()]
