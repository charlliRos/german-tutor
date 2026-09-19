"""The word inside its example sentence: find it (in whatever form), blank it out, check the answer."""
from __future__ import annotations

from dataclasses import dataclass

from .answers import ALMOST, CORRECT, WRONG, Check, _distance, normalize
from .content import _NOT_THE_WORD, _uses_word, bare_word

BLANK = "_____"


@dataclass
class Gap:
    sentence: str   # the example sentence
    blanked: str    # with the word replaced by BLANK
    form: str       # the word as it is written in the sentence (gehe, Häuser)


def _key(word) -> str:
    """The word to look for: the noun without its article, a verb without 'sich', a phrase's longest word."""
    tokens = [t for t in normalize(word.de).split() if t not in _NOT_THE_WORD]
    return max(tokens, key=len) if tokens else ""


def find_gap(word) -> Gap | None:
    """The example sentence with the word blanked out, or None if the word can't be found as one word
    (phrases, separable verbs split in two, irregular forms like ging for gehen)."""
    if not word.example_de or word.pos == "phrase" or len(normalize(word.de).split()) > 2:
        return None
    key = _key(word)
    if len(key) < 2:
        return None
    plural = normalize(word.plural).split()[-1] if word.plural and word.plural != "—" else ""
    parts = word.example_de.split()
    for i, part in enumerate(parts):
        core = bare_word(part)
        if core and _uses_word(normalize(core), key, word.pos, plural):
            start = part.lower().index(core)
            form = part[start:start + len(core)]
            parts[i] = part[:start] + BLANK + part[start + len(core):]
            return Gap(word.example_de, " ".join(parts), form)
    return None


def check_gap(answer: str, gap: Gap, word) -> Check:
    given, want = normalize(answer), normalize(gap.form)
    if given == want:
        return Check(CORRECT)
    if len(want) >= 5 and _distance(given, want) == 1:
        return Check(ALMOST, "Small spelling mistake.")
    if given and given in {normalize(word.de), _key(word)}:
        return Check(ALMOST, f"Right word! In this sentence it's {gap.form}.")
    return Check(WRONG)
