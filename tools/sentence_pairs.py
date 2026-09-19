"""Sentence-by-sentence English for book paragraphs (used by the look-back exercises).

  python tools/sentence_pairs.py export content/books/01_x.json work/01_x.todo.json
      Writes a to-do list: every translated paragraph without "sentences", split into German
      sentences, with an empty English slot per sentence and the paragraph's English as a guide.
  python tools/sentence_pairs.py import work/01_x.todo.json content/books/01_x.json
      Checks the filled-in list (one English sentence per German one) and saves it into the book
      as "sentences": [{"de": ..., "en": ...}] on each unit.

The split uses the app's own sentence splitter, so the German always matches what the app shows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.content import sentences  # noqa: E402


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def export(book_path: str, todo_path: str) -> None:
    book = _load(book_path)
    todo = []
    for unit in book["units"]:
        if unit.get("type") == "summary" or not unit.get("de") or not unit.get("en") or unit.get("sentences"):
            continue
        de = sentences(unit["de"])
        todo.append({"n": unit["n"], "paragraph_en": unit["en"], "de": de, "en": [""] * len(de)})
    _save(todo_path, todo)
    print(f"{len(todo)} paragraphs, {sum(len(t['de']) for t in todo)} sentences -> {todo_path}")


def import_(todo_path: str, book_path: str) -> None:
    todo, book = _load(todo_path), _load(book_path)
    units = {u["n"]: u for u in book["units"]}
    problems, done = [], 0
    for item in todo:
        unit = units.get(item["n"])
        if unit is None or not unit.get("de"):
            problems.append(f"unit {item['n']}: not a German unit in the book")
            continue
        if item["de"] != sentences(unit["de"]):
            problems.append(f"unit {item['n']}: German sentences changed since export")
            continue
        en = item.get("en", [])
        if len(en) != len(item["de"]) or not all(isinstance(e, str) and e.strip() for e in en):
            problems.append(f"unit {item['n']}: needs exactly {len(item['de'])} non-empty English sentences")
            continue
        unit["sentences"] = [{"de": d, "en": e.strip()} for d, e in zip(item["de"], en)]
        done += 1
    _save(book_path, book)
    print(f"{done} paragraphs saved to {book_path}")
    for p in problems:
        print("  problem:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("export", "import"):
        sys.exit(__doc__)
    (export if sys.argv[1] == "export" else import_)(sys.argv[2], sys.argv[3])
