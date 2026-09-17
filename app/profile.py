"""One progress file per kid: data/profiles/<name>.json (+ a translation journal)."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from . import srs
from .config import PROFILES_DIR


class Profile:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data
        for key, default in (("vocab", {}), ("books", {}), ("days", {}), ("current_book", None)):
            data.setdefault(key, default)

    @property
    def name(self) -> str:
        return self.data.get("name", self.path.stem)

    @property
    def journal_path(self) -> Path:
        return self.path.with_name(self.path.stem + "_journal.jsonl")

    @classmethod
    def list_all(cls) -> list["Profile"]:
        return [cls.load(p) for p in sorted(PROFILES_DIR.glob("*.json"))]

    @staticmethod
    def last_used(profiles: list["Profile"]) -> "Profile | None":
        """The profile saved most recently (every lesson step saves, so this is whoever practised last)."""
        return max(profiles, key=lambda p: p.path.stat().st_mtime, default=None)

    @classmethod
    def load(cls, path: Path) -> "Profile":
        with path.open(encoding="utf-8") as f:
            return cls(path, json.load(f))

    @classmethod
    def open_or_create(cls, name: str) -> "Profile":
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_").lower() or "student"
        path = PROFILES_DIR / f"{slug}.json"
        if path.exists():
            return cls.load(path)
        profile = cls(path, {"name": name.strip(), "created": date.today().isoformat()})
        profile.save()
        return profile

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def word_state(self, word_id: str) -> dict:
        return self.data["vocab"].setdefault(word_id, srs.new_state())

    def book_state(self, book_id: str) -> dict:
        return self.data["books"].setdefault(book_id, {"next": 1})

    def day(self, today: date) -> dict:
        return self.data["days"].setdefault(today.isoformat(), {"words": 0, "right": 0, "new": 0, "units": 0})

    def count(self, today: date, **amounts: int) -> None:
        day = self.day(today)
        for key, amount in amounts.items():
            day[key] = day.get(key, 0) + amount

    def streak(self, today: date) -> int:
        days = self.data["days"]
        d = today if today.isoformat() in days else today - timedelta(days=1)
        n = 0
        while d.isoformat() in days:
            n += 1
            d -= timedelta(days=1)
        return n

    def add_journal(self, entry: dict) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_journal(self, limit: int = 10) -> list[dict]:
        if not self.journal_path.exists():
            return []
        with self.journal_path.open(encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
        return entries[-limit:]
