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
        self.is_new = False  # created in this run (shows the first-time welcome)
        for key, default in (("vocab", {}), ("books", {}), ("days", {}), ("current_book", None)):
            data.setdefault(key, default)

    @property
    def name(self) -> str:
        return self.data.get("name", self.path.stem)

    @property
    def journal_path(self) -> Path:
        return self.path.with_name(self.path.stem + "_journal.jsonl")

    @classmethod
    def list_all(cls, unreadable: list[Path] | None = None) -> list["Profile"]:
        """All profiles. A damaged file is skipped (and added to `unreadable`) so the other kids still work."""
        profiles = []
        for path in sorted(PROFILES_DIR.glob("*.json")):
            try:
                profiles.append(cls.load(path))
            except (OSError, ValueError, AttributeError):
                if unreadable is not None:
                    unreadable.append(path)
        return profiles

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
        name = name.strip()
        legacy = PROFILES_DIR / f"{re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_').lower() or 'student'}.json"
        if legacy.exists() and cls.load(legacy).name.casefold() == name.casefold():
            return cls.load(legacy)  # created before file names kept letters like ü
        slug = re.sub(r"[^\w-]+", "_", name).strip("_").lower() or "student"
        n = 1
        while True:
            path = PROFILES_DIR / (f"{slug}.json" if n == 1 else f"{slug}_{n}.json")
            if not path.exists():
                break
            existing = cls.load(path)
            if existing.name.casefold() == name.casefold():
                return existing
            n += 1  # a different student already uses this file name
        profile = cls(path, {"name": name, "created": date.today().isoformat()})
        profile.is_new = True
        profile.save()
        return profile

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())  # on disk before it replaces the old file, so a power cut can't leave it empty
        os.replace(tmp, self.path)

    def word_state(self, word_id: str) -> dict:
        return self.data["vocab"].setdefault(word_id, srs.new_state())

    def book_state(self, book_id: str) -> dict:
        return self.data["books"].setdefault(book_id, {"next": 1})

    def day(self, today: date) -> dict:
        """Today's counters (read-only: an empty dict until something is practised)."""
        return self.data["days"].get(today.isoformat(), {})

    def count(self, today: date, **amounts: int) -> None:
        day = self.data["days"].setdefault(
            today.isoformat(), {"words": 0, "right": 0, "almost": 0, "new": 0, "units": 0, "warmups": 0})
        for key, amount in amounts.items():
            day[key] = day.get(key, 0) + amount

    def add_time(self, today: date, seconds: int) -> None:
        """Practice time, only on days something was practised (opening a lesson and quitting adds nothing)."""
        day = self.data["days"].get(today.isoformat())
        if day is not None and seconds > 0:
            day["seconds"] = day.get("seconds", 0) + seconds

    def practice_days(self, before: date) -> int:
        """Days with a finished warm-up before the given day (drives the warm-up size)."""
        return sum(1 for d, c in self.data["days"].items() if d < before.isoformat() and c.get("warmups", 0))

    @staticmethod
    def practised(counts: dict) -> bool:
        """A practice day: a finished warm-up or a finished paragraph (the streak and the report both use this)."""
        return bool(counts.get("warmups", 0) or counts.get("units", 0))

    def streak(self, today: date) -> int:
        """Consecutive practice days up to today (or yesterday, if today hasn't been practised yet)."""
        days = {d for d, c in self.data["days"].items() if self.practised(c)}
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

    def read_journal(self, limit: int | None = 10) -> list[dict]:
        if not self.journal_path.exists():
            return []
        with self.journal_path.open(encoding="utf-8") as f:
            entries = []
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass  # a half-written line (e.g. the computer turned off mid-save)
        return entries if limit is None else entries[-limit:]
