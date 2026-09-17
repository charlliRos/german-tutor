"""Turn a plain German text file into a book skeleton for content/books/.

Usage: python tools/split_text.py input.txt content/books/11_author_title.json --title "..." --author "..."

Splits into 40–110 word units at sentence boundaries and modernises a few common old
spellings. The English translation, explanation and key words are left empty: fill them
in (units without "en" are skipped by the app), then run tools/validate_content.py.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

OLD_SPELLINGS = {
    "daß": "dass", "Daß": "Dass", "muß": "muss", "mußte": "musste", "mußten": "mussten",
    "läßt": "lässt", "laß": "lass", "bißchen": "bisschen", "gewiß": "gewiss",
    "Schluß": "Schluss", "Fluß": "Fluss", "Kuß": "Kuss", "wußte": "wusste", "wußten": "wussten",
    "Thür": "Tür", "Thüre": "Tür", "Theil": "Teil", "seyn": "sein", "Thal": "Tal", "Noth": "Not",
}
MIN_WORDS, MAX_WORDS = 40, 110


def modernise(text: str) -> str:
    return re.sub(r"\b\w+\b", lambda m: OLD_SPELLINGS.get(m.group(0), m.group(0)), text)


def split_units(text: str) -> list[str]:
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    current = ""
    for para in paragraphs:
        for sentence in re.split(r"(?<=[.!?«»])\s+(?=[A-ZÄÖÜ»„])", para):
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate.split()) > MAX_WORDS:
                units.append(current)
                current = sentence
            else:
                current = candidate
        if len(current.split()) >= MIN_WORDS:
            units.append(current)
            current = ""
    if current:
        units.append(current)
    return units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    args = parser.parse_args()

    text = modernise(Path(args.input).read_text(encoding="utf-8"))
    units = [{"n": i, "de": de, "en": "", "explain_en": "", "words": []}
             for i, de in enumerate(split_units(text), 1)]
    book = {"id": Path(args.output).stem.split("_", 1)[-1].replace("_", "-"), "title": args.title,
            "author": args.author, "author_died": None, "year": None, "level": "", "source": "",
            "orthography": "modernised spelling", "intro_en": "", "units": units}
    Path(args.output).write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(units)} units to {args.output}")


if __name__ == "__main__":
    main()
