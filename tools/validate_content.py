"""Check every file in content/ against CONTENT_FORMAT.md.  Usage: python tools/validate_content.py"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import BOOKS_DIR, VOCAB_DIR  # noqa: E402
from app.content import BANKS, is_duplicate, sentences, vocab_files  # noqa: E402
from app.versions import compare, current_items, load_versions  # noqa: E402

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
    meanings: dict[str, list[set[str]]] = {}
    banks: Counter = Counter()
    for path in vocab_files(VOCAB_DIR):
        data = load(path)
        if data is None:
            continue
        bank = data.get("bank")
        if bank not in BANKS:
            errors.append(f"{path.name}: bank must be one of {', '.join(BANKS)}")
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
            if isinstance(w.get("en"), list) and is_duplicate(meanings, str(w.get("de", "")), w["en"]):
                warnings.append(f"{where}: {w.get('de')} with the same meaning is already in the bank, skipped by the app")
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
        for field in ("id", "title", "author", "year", "author_died", "level", "source", "intro_en", "units"):
            if not data.get(field):
                errors.append(f"{path.name}: missing {field}")
        died = data.get("author_died")
        if isinstance(died, int) and died + 70 >= date.today().year:
            errors.append(f"{path.name}: {data.get('author')} died in {died}: not public domain until "
                          f"1 January {died + 71} (life + 70 years)")
        units = data.get("units", [])
        for i, u in enumerate(units, 1):
            where = f"{path.name} unit {u.get('n', '?')}"
            if u.get("n") != i:
                errors.append(f"{where}: expected n={i}")
            if u.get("type") == "summary":
                if not u.get("en") or u.get("de"):
                    errors.append(f"{where}: a summary has English 'en' and no 'de'")
                if len(u.get("en", "").split()) > 160:
                    warnings.append(f"{where}: summary is long ({len(u['en'].split())} words, aim for 40–150)")
                continue
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
            pairs = u.get("sentences")
            if u.get("de") and u.get("en") and not pairs:
                warnings.append(f"{where}: no sentence-by-sentence English yet (tools/sentence_pairs.py)")
            elif pairs:
                if [p.get("de", "") for p in pairs] != sentences(u.get("de", "")):
                    errors.append(f"{where}: 'sentences' don't match the German text (it was edited, or the "
                                  "sentence splitter changed): remove 'sentences' and redo them with "
                                  "tools/sentence_pairs.py")
                if any(not p.get("en") for p in pairs):
                    errors.append(f"{where}: a sentence has no English")
        summary.append((data.get("title", path.stem), len(units)))
    return summary


def check_versions() -> None:
    """Every edit is recorded in content/item_versions.json (tools/item_versions.py), and paragraphs are
    never renumbered."""
    changes, refusals = compare(load_versions(), current_items())
    errors.extend(refusals)
    if changes:
        errors.append(f"{len(changes)} item(s) changed since content/item_versions.json was updated: "
                      "run python tools/item_versions.py --update")


def main() -> int:
    banks = check_vocab()
    books = check_books()
    check_versions()
    print("Vocabulary: " + ", ".join(f"{banks.get(b, 0)} {label}" for b, label in BANKS.items()) + " words")
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
