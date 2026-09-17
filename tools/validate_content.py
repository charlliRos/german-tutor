"""Check every file in content/ against CONTENT_FORMAT.md.  Usage: python tools/validate_content.py"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.answers import normalize  # noqa: E402
from app.config import BOOKS_DIR, VOCAB_DIR  # noqa: E402

POS = {"noun", "verb", "adj", "adv", "prep", "conj", "pron", "num", "phrase", "other"}
LEVELS = {"A1", "A2", "B1", "B2", "C1"}
ARTICLES = ("der ", "die ", "das ")

errors: list[str] = []
warnings: list[str] = []


def load(path: Path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: invalid JSON ({exc})")
        return None


def check_vocab() -> Counter:
    ids: Counter = Counter()
    de_seen: dict[str, str] = {}
    banks: Counter = Counter()
    for path in sorted(VOCAB_DIR.glob("*.json")):
        data = load(path)
        if data is None:
            continue
        bank = data.get("bank")
        if bank not in ("daily", "stem"):
            errors.append(f"{path.name}: bank must be 'daily' or 'stem'")
        for w in data.get("words", []):
            wid = w.get("id", "?")
            where = f"{path.name} {wid}"
            ids[wid] += 1
            banks[bank] += 1
            for field in ("id", "de", "en", "pos", "topic", "level", "rank", "example_de", "example_en"):
                if not w.get(field) and w.get(field) != 0:
                    errors.append(f"{where}: missing {field}")
            if w.get("pos") not in POS:
                errors.append(f"{where}: unknown pos {w.get('pos')!r}")
            if w.get("level") not in LEVELS:
                warnings.append(f"{where}: unusual level {w.get('level')!r}")
            if not isinstance(w.get("rank"), int):
                errors.append(f"{where}: rank must be an integer")
            if not isinstance(w.get("en"), list):
                errors.append(f"{where}: en must be a list")
            if w.get("pos") == "noun":
                if not str(w.get("de", "")).startswith(ARTICLES):
                    errors.append(f"{where}: noun without der/die/das: {w.get('de')!r}")
                if not w.get("plural"):
                    warnings.append(f"{where}: noun without plural")
            key = normalize(str(w.get("de", "")))
            if key in de_seen:
                warnings.append(f"{where}: same German as {de_seen[key]} ({w.get('de')}), skipped by the app")
            else:
                de_seen[key] = wid
    for wid, n in ids.items():
        if n > 1:
            errors.append(f"duplicate vocab id {wid} ({n}x)")
    return banks


def check_books() -> list[tuple[str, int]]:
    summary = []
    for path in sorted(BOOKS_DIR.glob("*.json")):
        data = load(path)
        if data is None:
            continue
        for field in ("id", "title", "author", "year", "level", "source", "intro_en", "units"):
            if not data.get(field):
                errors.append(f"{path.name}: missing {field}")
        units = data.get("units", [])
        for i, u in enumerate(units, 1):
            where = f"{path.name} unit {u.get('n', '?')}"
            if u.get("n") != i:
                errors.append(f"{where}: expected n={i}")
            for field in ("de", "en", "explain_en", "words"):
                if not u.get(field):
                    errors.append(f"{where}: missing {field}")
            n_words = len(re.findall(r"\w+", u.get("de", "")))
            if n_words > 130 or n_words < 15:
                warnings.append(f"{where}: {n_words} German words (aim for 40–110)")
            if re.search(r"\b(daß|muß|läßt|Thür|seyn)\b", u.get("de", "")):
                warnings.append(f"{where}: old spelling left in the text")
            for kw in u.get("words", []):
                if not kw.get("de") or not kw.get("en"):
                    errors.append(f"{where}: key word needs de and en: {kw}")
        summary.append((data.get("title", path.stem), len(units)))
    return summary


def main() -> int:
    banks = check_vocab()
    books = check_books()
    print(f"Vocabulary: {banks.get('daily', 0)} daily, {banks.get('stem', 0)} STEM words")
    for title, n in books:
        print(f"Book: {title} ({n} units)")
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
