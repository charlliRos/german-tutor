"""Pictures (SVG) inside the terminal: real pixels where the terminal can show them, coloured blocks elsewhere.

- sixel: a picture made of real pixels, drawn by the terminal itself (Windows Terminal, WezTerm, Konsole,
  foot, mlterm, xterm with sixel on). Sharp.
- blocks: each character cell shows two pixels (the upper-half block ▀ with a foreground and a background
  colour). Works in any terminal with colour; blocky but recognisable for simple pictures.
- off: no pictures (the written description is shown instead).
Chosen by "pictures" in config.json: "auto" (default), "sixel", "blocks" or "off".

SVGs are rendered by resvg (resvg-py, one small library with builds for Windows, macOS and Linux); its PNG is
decoded here with zlib and numpy, so no image library is needed. Pictures live in content/images/.
"""
from __future__ import annotations

import os
import sys
import zlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from rich.text import Text

from .config import CONTENT_DIR

IMAGES_DIR = CONTENT_DIR / "images"
BACKGROUND = (253, 251, 245)
SIXEL_TERMINALS = ("WezTerm", "konsole", "foot", "mlterm", "contour", "rio")


def mode(settings: dict) -> str:
    chosen = settings.get("pictures", "auto")
    if chosen in ("sixel", "blocks", "off"):
        return chosen
    if not sys.stdout.isatty():
        return "off"
    if os.environ.get("WT_SESSION"):          # Windows Terminal: sixel since version 1.22 (2025)
        return "sixel"
    program = os.environ.get("TERM_PROGRAM", "") + " " + os.environ.get("TERM", "")
    if os.environ.get("KONSOLE_VERSION") or any(t.lower() in program.lower() for t in SIXEL_TERMINALS):
        return "sixel"
    return "blocks"


# ----- rendering -----

def _decode_png(data: bytes) -> np.ndarray:
    """RGBA pixels (height, width, 4) from an 8-bit, non-interlaced RGBA or RGB PNG (what resvg writes)."""
    pos, width, height, channels, chunks = 8, 0, 0, 4, []
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
            channels = {6: 4, 2: 3}[body[9]]
        elif kind == b"IDAT":
            chunks.append(body)
        pos += 12 + length
    raw = np.frombuffer(zlib.decompress(b"".join(chunks)), dtype=np.uint8)
    stride = width * channels
    rows = raw.reshape(height, stride + 1)
    out = np.zeros((height, stride), dtype=np.int32)
    prev = np.zeros(stride, dtype=np.int32)
    for y in range(height):
        kind, line = rows[y, 0], rows[y, 1:].astype(np.int32)
        if kind == 0:
            cur = line
        elif kind == 2:
            cur = (line + prev) & 255
        else:  # Sub, Average, Paeth depend on the pixel to the left: go pixel by pixel
            cur = np.zeros(stride, dtype=np.int32)
            for x in range(stride):
                left = cur[x - channels] if x >= channels else 0
                up, up_left = prev[x], prev[x - channels] if x >= channels else 0
                if kind == 1:
                    guess = left
                elif kind == 3:
                    guess = (left + up) // 2
                else:
                    p = left + up - up_left
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                    guess = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
                cur[x] = (line[x] + guess) & 255
        out[y], prev = cur, cur
    pixels = out.reshape(height, width, channels).astype(np.uint8)
    if channels == 3:
        pixels = np.dstack([pixels, np.full((height, width), 255, np.uint8)])
    return pixels


@lru_cache(maxsize=64)
def render(path: str, width: int) -> np.ndarray | None:
    """The SVG at `path` as RGB pixels (height, width, 3) on the picture background; None if it can't be drawn."""
    try:
        import resvg_py
        png = resvg_py.svg_to_bytes(svg_path=str(path), width=int(width), background="#fdfbf5")
        rgba = _decode_png(bytes(png))
    except Exception:
        return None
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * alpha + np.array(BACKGROUND) * (1 - alpha)).astype(np.uint8)


# ----- showing -----

def blocks(pixels: np.ndarray) -> Text:
    """Two pixels per character: ▀ with the upper pixel as foreground and the lower one as background."""
    if pixels.shape[0] % 2:
        pixels = np.vstack([pixels, pixels[-1:]])
    text = Text()
    for y in range(0, pixels.shape[0], 2):
        for top, bottom in zip(pixels[y], pixels[y + 1]):
            text.append("▀", style=f"rgb({top[0]},{top[1]},{top[2]}) on rgb({bottom[0]},{bottom[1]},{bottom[2]})")
        text.append("\n")
    return text


def sixel(pixels: np.ndarray, colours: int = 64) -> str:
    """The picture as a sixel escape sequence: up to `colours` colours (quantised to a 4-4-4 grid), six pixel
    rows per band, run-length encoded."""
    height, width, _ = pixels.shape
    q = (pixels.astype(np.int32) * 15 + 127) // 255            # 0..15 per channel
    keys = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
    used, index = np.unique(keys, return_inverse=True)
    index = index.reshape(height, width)
    if len(used) > colours:  # keep the most common colours, map the rest to the nearest kept one
        counts = np.bincount(index.ravel())
        keep = np.argsort(-counts)[:colours]
        kept = np.stack([used[keep] // 256, used[keep] // 16 % 16, used[keep] % 16], axis=1)
        allc = np.stack([used // 256, used // 16 % 16, used % 16], axis=1)
        nearest = np.argmin(((allc[:, None, :] - kept[None, :, :]) ** 2).sum(-1), axis=1)
        index, used = nearest[index], used[keep]
    out = ["\x1bP0;1;0q", f'"1;1;{width};{height}']
    for n, key in enumerate(used):
        r, g, b = (int(key) // 256, int(key) // 16 % 16, int(key) % 16)
        out.append(f"#{n};2;{r * 100 // 15};{g * 100 // 15};{b * 100 // 15}")
    for top in range(0, height, 6):
        band = index[top:top + 6]
        for n in np.unique(band):
            bits = np.zeros(width, dtype=np.int32)
            for row in range(band.shape[0]):
                bits |= (band[row] == n).astype(np.int32) << row
            chars, run, last = [], 0, None
            for value in bits:
                c = chr(63 + int(value))
                if c == last:
                    run += 1
                    continue
                if last is not None:
                    chars.append(f"!{run}{last}" if run > 3 else last * run)
                last, run = c, 1
            chars.append(f"!{run}{last}" if run > 3 else last * run)
            out.append(f"#{n}" + "".join(chars) + "$")
        out.append("-")
    out.append("\x1b\\")
    return "".join(out)


def show_row(console, settings: dict, pictures: list[tuple[str, Path]], columns: int = 0) -> bool:
    """Show pictures side by side with their labels (a, b, c). False if they couldn't be shown."""
    how = mode(settings)
    if how == "off" or not pictures:
        return False
    columns = columns or console.width
    per = max(12, min(40, (columns - 2) // len(pictures) - 2))  # character columns per picture
    if how == "sixel":
        width_px = per * 9   # about 9 pixels per character column in a common terminal font
        rendered = [render(str(path), width_px) for _, path in pictures]
        if any(p is None for p in rendered):
            return False
        row = np.full((max(p.shape[0] for p in rendered), sum(p.shape[1] for p in rendered) + 18 * (len(rendered) - 1), 3),
                      BACKGROUND, np.uint8)
        x = 0
        for p in rendered:
            row[:p.shape[0], x:x + p.shape[1]] = p
            x += p.shape[1] + 18
        console.file.write(sixel(row) + "\n")
        console.file.flush()
        console.print("".join(label.center(per + 2) for label, _ in pictures), style="bold")
        return True
    rendered = [render(str(path), per) for _, path in pictures]
    if any(p is None for p in rendered):
        return False
    height = max(p.shape[0] for p in rendered)
    padded = [np.vstack([p, np.full((height - p.shape[0], p.shape[1], 3), BACKGROUND, np.uint8)]) for p in rendered]
    lines = [blocks(p).split("\n") for p in padded]
    for i in range(len(lines[0])):
        row = Text("  ").join(line[i] for line in lines if i < len(line))
        console.print(row, no_wrap=True)
    console.print("".join(label.center(per + 2) for label, _ in pictures), style="bold")
    return True
