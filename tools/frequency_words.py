"""The most common German words that the warm-up doesn't have yet, most common first.

Reads tools/data/de_frequency_top15k.txt (word forms from film and TV subtitles), turns each form into
its dictionary word (hast -> haben, Häuser -> Haus) and leaves out words already in content/vocab/.
The list still has names, English words and film-only words: whoever writes the entries skips those.

Needs simplemma (only for this tool, not for the app):  .venv/Scripts/pip install simplemma

Usage: python tools/frequency_words.py [--top 15000] [--out candidates.tsv]
Output (tab-separated): rank of the most common form, dictionary word, the forms seen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.answers import normalize  # noqa: E402
from app.config import VOCAB_DIR  # noqa: E402
from app.content import vocab_files  # noqa: E402

FREQUENCY_FILE = Path(__file__).resolve().parent / "data" / "de_frequency_top15k.txt"
ARTICLES = {"der", "die", "das"}


def bank_words() -> set[str]:
    """Every German headword in the bank (and its alternatives), normalised, without der/die/das."""
    words = set()
    for path in vocab_files(VOCAB_DIR):
        with path.open(encoding="utf-8") as f:
            for w in json.load(f)["words"]:
                for form in [w["de"], *w.get("de_alt", [])]:
                    parts = normalize(form).split()
                    if parts and parts[0] in ARTICLES:
                        parts = parts[1:]
                    words.add(" ".join(parts))
    return words


def candidates(top: int) -> list[tuple[int, str, list[str]]]:
    import simplemma
    known = bank_words()
    found: dict[str, tuple[int, list[str]]] = {}
    with FREQUENCY_FILE.open(encoding="utf-8") as f:
        forms = [line.split()[0] for line in f if line.strip() and not line.startswith("#")][:top]
    for rank, form in enumerate(forms, 1):
        if len(form) < 2 or not form.isalpha():
            continue
        lemma = simplemma.lemmatize(form, lang="de")
        if normalize(form) in known or normalize(lemma) in known:
            continue
        first, seen = found.setdefault(lemma.lower(), (rank, []))
        seen.append(form)
        found[lemma.lower()] = (first, seen)
    return sorted((rank, lemma, seen) for lemma, (rank, seen) in found.items())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=15000, help="how many of the most common forms to look at")
    parser.add_argument("--out", help="write here instead of printing")
    args = parser.parse_args()
    lines = [f"{rank}\t{lemma}\t{', '.join(forms)}" for rank, lemma, forms in candidates(args.top)]
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{len(lines)} words not in the bank yet -> {args.out}")
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
