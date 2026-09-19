"""Checking typed vocabulary answers.

Forgiving about case, punctuation, "to"/"the" prefixes and umlaut spelling
(ae/oe/ue/ss are accepted for ä/ö/ü/ß), strict about German noun genders.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

CORRECT, ALMOST, WRONG = "correct", "almost", "wrong"

ARTICLES = {"der", "die", "das"}
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_EN_PREFIXES = ("to ", "a ", "an ", "the ")


_PLAIN = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s"})
_TYPE_AS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


@dataclass
class Check:
    outcome: str
    message: str = ""
    overridable: bool = True  # may the kid say "my answer was right too"?


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


def _without_prefix(text: str) -> str:
    for prefix in _EN_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def check_english(answer: str, word) -> Check:
    # The answer itself isn't split on / or ;, so "to be / to go" can't hit by listing guesses.
    given = normalize(answer)
    if not given:
        return Check(WRONG, overridable=False)
    expected = set().union(*(english_forms(e) for e in word.en))
    if {given, _without_prefix(given)} & expected:
        return Check(CORRECT)
    # Typos are judged without "to"/"the", so "to do" isn't a misspelling of "to go".
    if any(_is_typo(_without_prefix(given), _without_prefix(e)) for e in expected):
        return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)


def _bare(text: str) -> str:
    """Normalised with umlauts reduced to plain letters (Tür -> tur), to spot a forgotten umlaut."""
    return normalize(unicodedata.normalize("NFC", text or "").lower().translate(_PLAIN))


def _umlaut_message(cand: str) -> str:
    marks = sorted({c for c in cand.lower() if c in _TYPE_AS})
    return (f"it's {cand} with {' and '.join(marks)} "
            f"(no key for it? type {' and '.join(_TYPE_AS[c] for c in marks)})")


def check_german(answer: str, word) -> Check:
    given = normalize(answer)
    if not given:
        return Check(WRONG, overridable=False)
    candidates = [word.de, *word.de_alt]
    if given in {normalize(c) for c in candidates}:
        return Check(CORRECT)

    given_article, given_rest = _split_article(given)
    _, bare_given_rest = _split_article(_bare(answer))
    for cand in candidates:
        norm = normalize(cand)
        article, rest = _split_article(norm)
        _, bare_rest = _split_article(_bare(cand))
        has_umlaut = any(c in cand.lower() for c in _TYPE_AS)
        if word.pos == "noun" and article:
            same_word = given_rest == rest
            umlaut = not same_word and has_umlaut and bare_given_rest == bare_rest
            typo = _is_typo(given_rest, rest)
            if (same_word or umlaut or typo) and given_article is None:
                extra = f" Also, {_umlaut_message(cand)}." if umlaut else ""
                return Check(ALMOST, f"Don't forget the article: {cand}.{extra}")
            if (same_word or umlaut) and given_article != article:
                return Check(WRONG, f"Right word, wrong article: it's {cand}.", overridable=False)
            if umlaut:
                return Check(ALMOST, f"It{_umlaut_message(cand)[2:]}.")
            if typo and given_article == article:
                return Check(ALMOST, "Small spelling mistake.")
        else:
            if has_umlaut and _bare(answer) == _bare(cand):
                return Check(ALMOST, f"It{_umlaut_message(cand)[2:]}.")
            if norm.startswith("sich ") and given == norm[5:]:
                return Check(ALMOST, f"It's reflexive: {cand}.")
            if _is_typo(given, norm):
                return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)


# Not a real try: random keys, a word or two for a whole text, or the given text copied back.
# Kept loose on purpose: an honest weak translation still shares plenty of words with the reference.
REAL_TRY_SHARE = 0.3    # at least this part of the typed words must be (close to) a word of the reference
REAL_TRY_LENGTH = 0.2   # and at least this many different words, for each word of the reference
COPIED_SOURCE = 0.85    # this similar to the text they were given = copied, not translated


def _close_to(word: str, words: set[str]) -> bool:
    """The word, or a misspelling of it (only for longer words: like/life, much/such are different words)."""
    return word in words or len(word) >= 6 and any(
        difflib.SequenceMatcher(a=word, b=w).ratio() >= 0.75 for w in words)


def real_try(answer: str, reference: str, source: str = "") -> str:
    """'' if `answer` looks like a real try at `reference`, else what's wrong with it.
    `source` is the text the kid was given (typing it back isn't translating)."""
    given, ref = normalize(answer).split(), normalize(reference).split()
    if not given or not ref:
        return ""
    if source and len(given) >= 3 and difflib.SequenceMatcher(
            a=normalize(answer), b=normalize(source), autojunk=False).ratio() >= COPIED_SOURCE:
        return "that's the text you were given, not a translation."
    ref_words = set(ref)
    # Longer words only, when there are some: "the", "and", "is" fit any text.
    content = [w for w in given if len(w) >= 4] or given
    if sum(_close_to(w, ref_words) for w in content) < REAL_TRY_SHARE * len(content):
        return "that doesn't match the text at all."
    if len(ref) >= 5 and len(set(given)) < REAL_TRY_LENGTH * len(ref):
        return "that's far too short for this text."
    return ""
