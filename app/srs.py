"""Spaced repetition (Leitner boxes): words you know come back less and less often."""
from __future__ import annotations

from datetime import date, timedelta

from .answers import ALMOST, CORRECT

MAX_BOX = 5
INTERVALS = {1: 1, 2: 3, 3: 7, 4: 16, 5: 35}  # days until the next review, per box
LEARNED_BOX = 3


def new_state() -> dict:
    return {"box": 0, "due": None, "seen": 0, "right": 0, "wrong": 0, "last": None}


def apply_result(state: dict, outcome: str, today: date) -> None:
    for key, value in new_state().items():
        state.setdefault(key, value)
    state["seen"] += 1
    state["last"] = today.isoformat()
    if outcome == CORRECT:
        state["box"] = min(state["box"] + 1, MAX_BOX)
        state["right"] += 1
        days = INTERVALS[state["box"]]
    elif outcome == ALMOST:
        state["box"] = max(state["box"], 1)
        days = 1
    else:
        state["box"] = 1
        state["wrong"] += 1
        days = 1
    state["due"] = (today + timedelta(days=days)).isoformat()


def mark_practised(state: dict, today: date) -> None:
    """Said out loud but not graded: keep the box, look again tomorrow."""
    for key, value in new_state().items():
        state.setdefault(key, value)
    state["seen"] += 1
    state["last"] = today.isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    if not state["due"] or state["due"] < tomorrow:
        state["due"] = tomorrow


def plan_session(states: dict, words: dict, settings: dict, today: date, new_so_far: int = 0):
    """Return (review_ids, new_ids) for today's warm-up. Overdue reviews come first."""
    t = today.isoformat()
    due = [wid for wid, s in states.items()
           if wid in words and s.get("box", 0) >= 1 and s.get("due") and s["due"] <= t]
    due.sort(key=lambda wid: (states[wid]["due"], states[wid]["box"]))
    size = int(settings["warmup_words"])
    reviews = due[:size]
    new_count = max(0, min(int(settings["new_words_per_day"]) - new_so_far, size - len(reviews)))
    return reviews, pick_new_words(states, words, new_count, float(settings["stem_share"]))


def pick_new_words(states: dict, words: dict, count: int, stem_share: float) -> list[str]:
    if count <= 0:
        return []
    unseen = sorted((w for w in words.values() if states.get(w.id, {}).get("box", 0) == 0),
                    key=lambda w: (w.rank, w.id))
    stem = [w.id for w in unseen if w.bank == "stem"]
    daily = [w.id for w in unseen if w.bank != "stem"]
    n_stem = min(round(count * stem_share), len(stem))
    n_daily = min(count - n_stem, len(daily))
    n_stem = min(count - n_daily, len(stem))  # top up from STEM if daily ran out
    return daily[:n_daily] + stem[:n_stem]
