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

from .answers import normalize
from .coverage import FUNCTION_WORDS, _index, _lookup

GREETING = {"informal": r"^\s*(liebe[rs]?|hallo|hi|hey|servus|moin)\b", "formal": r"^\s*(sehr geehrte[rs]?|guten tag)\b"}
CLOSING = {"informal": r"(viele|liebe|herzliche|beste|schöne)\s+grü(ß|ss)e|bis\s+(bald|dann|morgen|später)|\blg\b|tschüss|ciao",
           "formal": r"(mit\s+)?freundliche[n]?\s+grü(ß|ss)e[n]?|hochachtungsvoll"}
LINKERS = ("weil", "dass", "denn", "deshalb", "deswegen", "aber", "wenn", "obwohl", "trotzdem", "außerdem", "ausserdem",
           "damit", "als", "dann", "danach", "sondern", "oder", "zuerst", "schließlich", "schliesslich", "also")
LINKERS_NEEDED = {"A1": 1, "A2": 1, "B1": 3, "B2": 4}
MAX_TYPOS = 6


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
    low = " " + " ".join(text.lower().split()) + " "
    return [any(k.lower() in low for k in words) for words in point_keywords]


def check(text: str, part, level: str, content) -> WritingCheck:
    result = WritingCheck()
    words = len(text.split())
    low_min, target = part.words
    result.checks.append(Check("Length", words >= low_min,
                               f"{words} words (at least {low_min}, about {target})"))
    if part.point_keywords:
        result.points_found = points_found(text, part.point_keywords)
        missing = [p for p, ok in zip(part.points, result.points_found) if not ok]
        result.checks.append(Check("The task's points", not missing,
                                   f"{sum(result.points_found)} of {len(part.points)} found"
                                   + (f"; check: {'; '.join(missing)}" if missing else "")))
    kind = getattr(part, "kind", "")
    if kind in GREETING:
        lines = [l for l in text.splitlines() if l.strip()]
        greets = bool(lines) and re.search(GREETING[kind], lines[0].lower()) is not None
        closes = re.search(CLOSING[kind], text.lower()) is not None
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
    return result
