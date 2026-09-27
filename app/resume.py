"""Carry on where you stopped: today's bookmark in the profile, so a kid who leaves the app in the middle of a
lesson (or presses q) carries on from there next time instead of starting the lesson again.

profile.data["resume"] = {"date": "2026-09-28", "lesson": "warmup" | "reading" | "exam",
                          "warmup": {...}, "reading": {...}, "exam": {...}, "extras": {...}}
"extras": the first warm-up's verbs, der/die/das and grammar, still owed ({"verbs": [cards still to ask], ...}).
Each part is saved after every answer and dropped when that part is finished. A bookmark from another day is
ignored (and dropped). The same design as de-tutor's (crates/de-tutor-core/src/profile.rs, Resume).
"""
from __future__ import annotations


def today(ctx) -> dict | None:
    """Today's bookmark, or None. Another day's is dropped."""
    mark = ctx.profile.data.get("resume")
    if mark and mark.get("date") != ctx.today.isoformat():
        ctx.profile.data.pop("resume", None)
        return None
    return mark


def part(ctx, name: str) -> dict | None:
    """One part of today's bookmark ("warmup", "reading", "exam"), or None."""
    mark = today(ctx)
    return mark.get(name) if mark else None


def bookmark(ctx) -> dict:
    """Today's bookmark, made if there's none."""
    mark = today(ctx)
    if mark is None:
        mark = ctx.profile.data["resume"] = {"date": ctx.today.isoformat()}
    return mark


def set_part(ctx, name: str, value) -> None:
    bookmark(ctx)[name] = value


def extras_todo(ctx, name: str, planned: list) -> list:
    """What part `name` ("verbs", "genders", "grammar") of the day's extras still has to ask. The first time,
    `planned` is kept in the bookmark; later the same day the kept rest comes back, so a kid who stopped
    halfway finishes the day's cards and nothing is asked twice. Without an "extras" bookmark: `planned`."""
    extras = part(ctx, "extras")
    if extras is None:
        return planned
    return list(extras.setdefault(name, list(planned)))


def extras_done(ctx, name: str, item) -> None:
    """One item of the day's extras is answered: it's off the list."""
    extras = part(ctx, "extras")
    if extras is not None and item in extras.get(name, []):
        extras[name].remove(item)


def clear(ctx, name: str) -> None:
    """A part is finished: drop it (and the whole bookmark when nothing is left in it)."""
    mark = today(ctx)
    if mark is None:
        return
    mark.pop(name, None)
    if set(mark) <= {"date"}:
        ctx.profile.data.pop("resume", None)
