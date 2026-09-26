"""Examiner-style checks on an exam writing task (no AI: word lists and the word bank). An estimate, shown
next to the model answer, so a kid sees what an examiner would look at first:

- length: at least the minimum, close to the target;
- the task's points: found by their keywords (point_keywords in the exam file);
- greeting and closing that fit the kind of text (an email to a friend, a formal message);
- linking words (weil, dass, deshalb …), which the B1 marking asks for;
- nouns with a capital letter;
- words the word bank doesn't know (possible spelling mistakes).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .answers import _distance, normalize
from .coverage import FUNCTION_WORDS, _index, _lookup

GREETING = {"informal": r"^\s*(liebe[rs]?|hallo|hi|hey|servus|moin)\b", "formal": r"^\s*(sehr geehrte[rs]?|guten tag)\b"}
CLOSING = {"informal": r"(viele|liebe|herzliche|beste|schöne)\s+grü(ß|ss)e|bis\s+(bald|dann|morgen|später)|\blg\b|tschüss|ciao",
           "formal": r"(mit\s+)?freundliche[n]?\s+grü(ß|ss)e[n]?|hochachtungsvoll"}
LINKERS = ("weil", "dass", "denn", "deshalb", "deswegen", "aber", "wenn", "obwohl", "trotzdem", "außerdem", "ausserdem",
           "damit", "als", "dann", "danach", "sondern", "oder", "zuerst", "schließlich", "schliesslich", "also")
LINKERS_NEEDED = {"A1": 1, "A2": 1, "B1": 3, "B2": 4}
MAX_TYPOS = 6
GREETING_CLOSING = "#greeting_closing"  # a point_keywords list of just this: the point is the greeting + closing check
SUBORDINATE = ("weil", "dass", "obwohl", "ob", "wenn", "bevor", "nachdem")  # a comma before, the verb at the end
NO_COMMA_AFTER = {"und", "oder", "sondern", "aber", "auch", "nur", "so", "als"}
OFTEN = 3        # a content word used this often (in a text of REPEAT_FROM words or more): vary it
REPEAT_FROM = 30


def mentions(text: str, phrase: str) -> bool:
    """Does the text contain the phrase? Forgiving: a phrase of one longer word also matches a longer form
    (entschuldig → Entschuldigung) or a one-letter slip (sporz → sport), so a small typo or a speech-check
    mishearing doesn't hide a point that was made."""
    tokens = normalize(text).split()
    want = normalize(phrase).split()
    if not want:
        return False
    if " " + " ".join(want) + " " in " " + " ".join(tokens) + " " or any(t.startswith(want[0]) for t in tokens if len(want) == 1):
        return True
    if len(want) == 1 and len(want[0]) >= 5:
        return any(_distance(t[:len(want[0])], want[0]) <= 1 for t in tokens if len(t) >= len(want[0]) - 1)
    return False


def is_verb(content, index, token: str) -> bool:
    ids = _lookup(index, token)
    return bool(ids) and any(content.words[i].pos == "verb" for i in ids)


@dataclass
class Check:
    label: str
    ok: bool
    detail: str = ""


@dataclass
class WritingCheck:
    checks: list[Check] = field(default_factory=list)
    points_found: list[bool] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(c.ok for c in self.checks)


def points_found(text: str, point_keywords: list[list[str]]) -> list[bool]:
    return [any(mentions(text, k) for k in words) for words in point_keywords]


def check(text: str, part, level: str, content) -> WritingCheck:
    result = WritingCheck()
    words = len(text.split())
    low_min, target = part.words
    result.checks.append(Check("Length", words >= low_min,
                               f"{words} words (at least {low_min}, about {target})"))
    kind = getattr(part, "kind", "")
    greets_and_closes = None
    if kind in GREETING:
        lines = [l for l in text.splitlines() if l.strip()]
        greets = bool(lines) and re.search(GREETING[kind], lines[0].lower()) is not None
        closes = re.search(CLOSING[kind], text.lower()) is not None
        greets_and_closes = greets and closes
    if part.point_keywords:
        result.points_found = [bool(greets_and_closes) if words == [GREETING_CLOSING] else found
                               for words, found in zip(part.point_keywords, points_found(text, part.point_keywords))]
        missing = [p for p, ok in zip(part.points, result.points_found) if not ok]
        result.checks.append(Check("The task's points", not missing,
                                   f"{sum(result.points_found)} of {len(part.points)} found"
                                   + (f"; check: {'; '.join(missing)}" if missing else "")))
    if kind in GREETING:
        example = "Liebe Anna, … Viele Grüße" if kind == "informal" else "Sehr geehrte Frau …, … Mit freundlichen Grüßen"
        result.checks.append(Check("Greeting and closing", greets and closes,
                                   "both there" if greets and closes else
                                   f"{'greeting' if not greets else 'closing'} missing (e.g. {example})"))
        if kind == "formal" and re.search(r"\b(du|dich|dir|dein\w*)\b", text.lower()):
            result.checks.append(Check("Formal: Sie, not du", False, "a formal message uses Sie / Ihnen / Ihr"))
    tokens = normalize(text).split()
    used = sorted({t for t in tokens if t in LINKERS})
    needed = LINKERS_NEEDED.get(level, 1)
    result.checks.append(Check("Linking words", len(used) >= needed,
                               (", ".join(used) if used else "none") + f" (aim for {needed}+: weil, dass, deshalb …)"))
    index = _index(content)
    lowercase_nouns, typos = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        raw = re.findall(r"[A-Za-zÄÖÜäöüß]+", sentence)
        for i, word in enumerate(raw):
            token = normalize(word)
            ids = _lookup(index, token)
            if ids and i > 0 and word[0].islower() and all(content.words[w].pos == "noun" for w in ids):
                lowercase_nouns.append(word)
            elif not ids and token not in FUNCTION_WORDS and len(token) >= 4 and word[0].islower():
                typos.append(word)
    result.checks.append(Check("Nouns with a capital", not lowercase_nouns,
                               "all fine" if not lowercase_nouns else "write with a capital: " + ", ".join(dict.fromkeys(lowercase_nouns))))
    result.checks.append(Check("Spelling (words the app doesn't know)", not typos,
                               "none" if not typos else "check: " + ", ".join(list(dict.fromkeys(typos))[:MAX_TYPOS])))
    missing_comma = [m.group(2) for m in re.finditer(r"(\w+)\s+(" + "|".join(SUBORDINATE) + r")\b", text, re.I)
                     if m.group(1).lower() not in NO_COMMA_AFTER]
    result.checks.append(Check("Comma before weil / dass / wenn …", not missing_comma,
                               "all fine" if not missing_comma else
                               f"put a comma before: {', '.join(dict.fromkeys(w.lower() for w in missing_comma))}"))
    verb_not_last = []
    for m in re.finditer(r"\b(" + "|".join(SUBORDINATE) + r")\b([^,.!?;:]*)", text, re.I):
        clause = normalize(m.group(2)).split()
        if len(clause) >= 3 and is_verb(content, index, clause[1]) and not is_verb(content, index, clause[-1]):
            verb_not_last.append(f"{m.group(1).lower()} {' '.join(clause[:3])} …")
    result.checks.append(Check("Verb at the end after weil / dass …", not verb_not_last,
                               "all fine" if not verb_not_last else
                               "check: " + "; ".join(verb_not_last[:3]) + " (weil ich krank bin, not weil ich bin krank)"))
    if words >= REPEAT_FROM:
        counts: dict[str, int] = {}
        for t in tokens:
            if len(t) >= 4 and t not in FUNCTION_WORDS and t not in LINKERS:
                counts[t] = counts.get(t, 0) + 1
        often = [f"{t} ({n}×)" for t, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= OFTEN]
        result.checks.append(Check("Different words", not often,
                                   "good variety" if not often else "used often: " + ", ".join(often[:4])))
    return result
