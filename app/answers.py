"""Checking typed vocabulary answers.

Forgiving about case, punctuation, "to"/"the" prefixes and umlaut spelling
(ae/oe/ue/ss are accepted for ä/ö/ü/ß), strict about German noun genders.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CORRECT, ALMOST, WRONG = "correct", "almost", "wrong"

ARTICLES = {"der", "die", "das"}
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_EN_PREFIXES = ("to ", "a ", "an ", "the ")


@dataclass
class Check:
    outcome: str
    message: str = ""


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)  # drop "(something)" hints
    text = text.translate(_UMLAUTS)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"['’`\-]", "", text)  # E-Mail == Email, geht's == gehts
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def english_forms(text: str) -> set[str]:
    """All accepted spellings of one English answer, e.g. 'to go' -> {'to go', 'go'}."""
    forms = set()
    for alt in re.split(r"[/;]", text):
        n = normalize(alt)
        if not n:
            continue
        forms.add(n)
        for prefix in _EN_PREFIXES:
            if n.startswith(prefix):
                forms.add(n[len(prefix):])
    return forms


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_typo(given: str, expected: str) -> bool:
    if len(expected) < 5 or abs(len(given) - len(expected)) > 2:
        return False
    allowed = 2 if len(expected) >= 10 else 1
    return 0 < _distance(given, expected) <= allowed


def _split_article(text: str) -> tuple[str | None, str]:
    first, _, rest = text.partition(" ")
    if rest and first in ARTICLES:
        return first, rest
    return None, text


def check_english(answer: str, word) -> Check:
    given = english_forms(answer)
    if not given:
        return Check(WRONG, "No answer — that's OK, now you know it.")
    expected = set().union(*(english_forms(e) for e in word.en))
    if given & expected:
        return Check(CORRECT)
    if any(_is_typo(g, e) for g in given for e in expected):
        return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)


def check_german(answer: str, word) -> Check:
    given = normalize(answer)
    if not given:
        return Check(WRONG, "No answer — that's OK, now you know it.")
    candidates = [word.de, *word.de_alt]
    normalized = [normalize(c) for c in candidates]
    if given in normalized:
        return Check(CORRECT)

    given_article, given_rest = _split_article(given)
    for cand, norm in zip(candidates, normalized):
        article, rest = _split_article(norm)
        if word.pos == "noun" and article:
            same_word = given_rest == rest
            if (same_word or _is_typo(given_rest, rest)) and given_article is None:
                return Check(ALMOST, f"Don't forget the article: {cand}")
            if same_word and given_article != article:
                return Check(WRONG, f"Right word, wrong article — it's {cand}")
            if _is_typo(given_rest, rest) and given_article == article:
                return Check(ALMOST, "Small spelling mistake.")
        else:
            if norm.startswith("sich ") and given == norm[5:]:
                return Check(ALMOST, f"It's reflexive: {cand}")
            if _is_typo(given, norm):
                return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)
