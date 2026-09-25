"""Record what changed in content/ since the last time: python tools/item_versions.py [--update]

Without --update it only reports (and exits 1 if content/item_versions.json is out of date, so
validate_content.py and the tests catch a forgotten update). With --update it bumps the version of every
changed item and notes whether the answer, the wording or only the presentation changed (app/versions.py).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.versions import compare, current_items, load_versions, save_versions, update  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="write the new versions")
    args = parser.parse_args(argv)
    recorded, current = load_versions(), current_items()
    changes, refusals = compare(recorded, current)
    for reason in refusals:
        print(f"  REFUSED: {reason}")
    counts = Counter(what for _, what in changes)
    for item_id, what in changes[:40]:
        print(f"  {what:12} {item_id}")
    if len(changes) > 40:
        print(f"  … and {len(changes) - 40} more")
    print(", ".join(f"{n} {what}" for what, n in counts.items()) or "No changes.")
    if refusals:
        print("Nothing written: fix the refused items first.")
        return 1
    if args.update and changes:
        save_versions(update(recorded, current, changes, date.today()))
        print("content/item_versions.json updated.")
        return 0
    return 1 if changes else 0


if __name__ == "__main__":
    sys.exit(main())
