"""Make a ready-made PNG next to every SVG picture: python tools/render_pictures.py

The app draws SVGs with resvg; where that can't run (Windows' Smart App Control blocks its unsigned file), it
shows these PNGs instead (app/pictures.py). Run it after adding or changing pictures.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pictures import IMAGES_DIR, PREPARED_WIDTH, encode_png, render  # noqa: E402


def main() -> int:
    made = 0
    for svg in sorted(IMAGES_DIR.rglob("*.svg")):
        pixels = render(str(svg), PREPARED_WIDTH)
        if pixels is None:
            print(f"  can't draw {svg.relative_to(IMAGES_DIR)}")
            continue
        svg.with_suffix(".png").write_bytes(encode_png(pixels))
        made += 1
    print(f"{made} PNGs written next to the SVGs in content/images/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
