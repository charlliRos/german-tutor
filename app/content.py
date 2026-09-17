"""Loads the vocabulary bank and books from content/ (see CONTENT_FORMAT.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .answers import normalize
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
    n: int
    de: str
    en: str
    explain_en: str = ""
    words: list[dict] = field(default_factory=list)


@dataclass
class Book:
    id: str
    title: str
    author: str
    year: int | str
    level: str
    intro_en: str
    units: list[Unit]


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


def load_content(vocab_dir: Path = VOCAB_DIR, books_dir: Path = BOOKS_DIR) -> Content:
    content = Content()
    seen_de: dict[str, str] = {}
    # daily_* sorts before stem_*, so everyday words win when both banks have a word.
    for path in sorted(vocab_dir.glob("*.json")):
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
            key = normalize(word.de)
            if key in seen_de:
                continue  # same German word already in the bank
            seen_de[key] = word.id
            content.words[word.id] = word

    for path in sorted(books_dir.glob("*.json")):
        data = _load_json(path, content.problems)
        if not data:
            continue
        units = []
        for raw in data.get("units", []):
            if not raw.get("de") or not raw.get("en"):
                continue  # not translated yet
            units.append(Unit(n=len(units) + 1, de=raw["de"].strip(), en=raw["en"].strip(),
                              explain_en=raw.get("explain_en", ""), words=raw.get("words", [])))
        if not units:
            content.problems.append(f"{path.name}: no translated units")
            continue
        content.books.append(Book(
            id=data.get("id", path.stem), title=data.get("title", path.stem),
            author=data.get("author", ""), year=data.get("year", ""), level=data.get("level", ""),
            intro_en=data.get("intro_en", ""), units=units,
        ))
    return content


def words_sharing_english(content: Content, word: Word) -> list[Word]:
    """Other bank words with an overlapping English meaning (wissen/kennen for 'to know')."""
    from .answers import english_forms

    mine = set().union(*(english_forms(e) for e in word.en))
    return [w for w in content.words.values()
            if w.id != word.id and mine & set().union(*(english_forms(e) for e in w.en))]
