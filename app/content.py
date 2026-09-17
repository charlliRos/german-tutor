"""Loads the vocabulary bank and books from content/ (see CONTENT_FORMAT.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .answers import english_forms, normalize
from .config import BOOKS_DIR, VOCAB_DIR


@dataclass
class Word:
    id: str
    bank: str
    de: str
    en: list[str]
    pos: str
    topic: str = ""
    level: str = ""
    rank: int = 9999
    de_alt: list[str] = field(default_factory=list)
    plural: str = ""
    note: str = ""
    example_de: str = ""
    example_en: str = ""


@dataclass
class Unit:
    n: int                 # position in the book (1-based), used for progress
    de: str
    en: str
    explain_en: str = ""
    words: list[dict] = field(default_factory=list)
    kind: str = "text"     # "text" = German lesson, "summary" = English bridge over skipped parts
    part: int = 0          # lesson number counting only text units
    covers: str = ""


@dataclass
class Book:
    id: str
    title: str
    author: str
    year: int | str
    level: str
    intro_en: str
    units: list[Unit]
    total_parts: int = 0   # German units in the file, including ones not translated yet

    @property
    def parts(self) -> int:
        return sum(1 for u in self.units if u.kind == "text")

    def parts_read(self, next_n: int) -> int:
        return sum(1 for u in self.units if u.kind == "text" and u.n < next_n)

    def next_unit(self, next_n: int) -> Unit | None:
        """The first loaded unit at or after position next_n (untranslated units are skipped)."""
        return next((u for u in self.units if u.n >= next_n), None)


@dataclass
class Content:
    words: dict[str, Word] = field(default_factory=dict)
    books: list[Book] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _as_list(value) -> list[str]:
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]


def _load_json(path: Path, problems: list[str]):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.name}: cannot read ({exc})")
        return None


BANKS = {"daily": "everyday", "stem": "STEM", "admin": "official German"}


def vocab_files(vocab_dir: Path = VOCAB_DIR) -> list[Path]:
    """Everyday lists first, then STEM, then official German, so a shared word stays in the most basic list."""
    order = list(BANKS)
    return sorted(vocab_dir.glob("*.json"),
                  key=lambda p: (order.index(p.stem.split("_")[0]) if p.stem.split("_")[0] in order else 9, p.name))


def meaning_key(de: str, en: list[str]) -> tuple[str, set[str]]:
    return normalize(de), set().union(*(english_forms(e) for e in en))


def is_duplicate(seen: dict[str, list[set[str]]], de: str, en: list[str]) -> bool:
    """Same German AND an overlapping English meaning. 'gerade' = straight vs. even (number) are both kept."""
    key, meanings = meaning_key(de, en)
    if any(meanings & other for other in seen.get(key, [])):
        return True
    seen.setdefault(key, []).append(meanings)
    return False


def load_content(vocab_dir: Path = VOCAB_DIR, books_dir: Path = BOOKS_DIR) -> Content:
    content = Content()
    seen_meanings: dict[str, list[set[str]]] = {}
    for path in vocab_files(vocab_dir):
        data = _load_json(path, content.problems)
        if not data:
            continue
        bank = data.get("bank", "daily")
        for raw in data.get("words", []):
            try:
                word = Word(
                    id=str(raw["id"]), bank=bank, de=raw["de"].strip(), en=_as_list(raw["en"]),
                    pos=raw.get("pos", "other"), topic=raw.get("topic", ""), level=raw.get("level", ""),
                    rank=int(raw.get("rank", 9999)), de_alt=_as_list(raw.get("de_alt")),
                    plural=raw.get("plural", ""), note=raw.get("note", ""),
                    example_de=raw.get("example_de", ""), example_en=raw.get("example_en", ""),
                )
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                content.problems.append(f"{path.name}: bad word entry {raw!r:.60} ({exc})")
                continue
            if not word.en:
                content.problems.append(f"{path.name}: {word.id} has no English")
                continue
            if word.id in content.words:
                content.problems.append(f"{path.name}: duplicate id {word.id}")
                continue
            if is_duplicate(seen_meanings, word.de, word.en):
                continue  # already in the bank with the same meaning
            content.words[word.id] = word

    for path in sorted(books_dir.glob("*.json")):
        data = _load_json(path, content.problems)
        if not data:
            continue
        units: list[Unit] = []
        part = 0
        # n and part are positions in the file (counting untranslated units too), so saved progress
        # stays valid when a skipped unit gets translated later.
        for n, raw in enumerate(data.get("units", []), 1):
            if raw.get("type") == "summary":
                if raw.get("en"):
                    units.append(Unit(n=n, de="", en=raw["en"].strip(), kind="summary",
                                      covers=raw.get("covers", "")))
                continue
            part += 1
            if not raw.get("de") or not raw.get("en"):
                continue  # not translated yet
            units.append(Unit(n=n, de=raw["de"].strip(), en=raw["en"].strip(), part=part,
                              explain_en=raw.get("explain_en", ""), words=raw.get("words", [])))
        if not any(u.kind == "text" for u in units):
            content.problems.append(f"{path.name}: no translated units")
            continue
        content.books.append(Book(
            id=data.get("id", path.stem), title=data.get("title", path.stem),
            author=data.get("author", ""), year=data.get("year", ""), level=data.get("level", ""),
            intro_en=data.get("intro_en", ""), units=units, total_parts=part,
        ))
    return content


def words_sharing_english(content: Content, word: Word) -> list[Word]:
    """Other bank words with an overlapping English meaning (wissen/kennen for 'to know')."""
    mine = set().union(*(english_forms(e) for e in word.en))
    return [w for w in content.words.values()
            if w.id != word.id and mine & set().union(*(english_forms(e) for e in w.en))]
