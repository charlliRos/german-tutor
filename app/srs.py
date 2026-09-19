"""Spaced repetition (Leitner boxes): words you know come back less and less often."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .answers import ALMOST, CORRECT, WRONG

READING = "reading"  # same as content.READING (no import: content imports answers)

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


def apply_practice(state: dict, outcome: str, today: date) -> None:
    """Extra practice beyond what's due: a miss brings the word back sooner, a hit doesn't skip ahead."""
    if outcome == WRONG:
        apply_result(state, WRONG, today)
        return
    for key, value in new_state().items():
        state.setdefault(key, value)
    state["seen"] += 1
    state["last"] = today.isoformat()
    state["right"] += outcome == CORRECT


def warmup_size(settings: dict, practice_days: int) -> int:
    """Starts small and grows with every day of practice, up to the maximum."""
    start, top = int(settings["warmup_start"]), int(settings["warmup_max"])
    return min(top, start + int(float(settings["warmup_growth"]) * practice_days))


def new_word_cap(settings: dict, size: int) -> int:
    return max(int(settings["min_new_words"]), round(size * float(settings["new_word_share"])))


@dataclass
class Plan:
    reviews: list[str]
    new: list[str]
    practice: list[str]

    @property
    def total(self) -> int:
        return len(self.reviews) + len(self.new) + len(self.practice)


def reading_words_due(words: dict, queue: list[str], count: int) -> list[str]:
    """Key words of paragraphs already read, oldest first: new ones AND ones already known, because
    meeting a word again in a story is more repetition, and repetition is how words stick."""
    return [wid for wid in queue if wid in words][: max(count, 0)]


def plan_session(states: dict, words: dict, settings: dict, today: date, size: int, new_allowed: int) -> Plan:
    """Fill a warm-up of `size` words: some new words (always a few, if allowed), then due reviews
    (most overdue first), then extra practice on words already started (weakest, least recent first).
    If there is still room (early on, few words have been started), it is topped up with new words,
    so a warm-up is always full while the bank has words left."""
    t = today.isoformat()
    shares = settings["bank_shares"]
    new = pick_new_words(states, words, min(max(new_allowed, 0), size), shares)
    due = [wid for wid, s in states.items()
           if wid in words and s.get("box", 0) >= 1 and s.get("due") and s["due"] <= t]
    due.sort(key=lambda wid: (states[wid]["due"], states[wid]["box"]))
    reviews = due[: size - len(new)]
    taken = set(reviews)
    started = [wid for wid, s in states.items() if wid in words and s.get("box", 0) >= 1 and wid not in taken]
    started.sort(key=lambda wid: (states[wid].get("last") == t, states[wid]["box"], states[wid].get("last") or ""))
    practice = started[: size - len(new) - len(reviews)]
    room = size - len(new) - len(reviews) - len(practice)
    if room > 0:
        new = pick_new_words(states, words, len(new) + room, shares)
    return Plan(reviews, new, practice)


def pick_new_words(states: dict, words: dict, count: int, shares: dict[str, float]) -> list[str]:
    """Pick the most common unseen words, mixing the banks (daily, stem, admin) by their share.
    Words from the books never come this way: they join once their paragraph is read."""
    pools: dict[str, list[str]] = {}
    for w in sorted(words.values(), key=lambda w: (w.rank, w.id)):
        if w.bank != READING and states.get(w.id, {}).get("box", 0) == 0:
            pools.setdefault(w.bank, []).append(w.id)
    taken = {bank: 0 for bank in pools}
    picked: list[str] = []
    for k in range(1, count + 1):
        open_banks = [b for b in pools if taken[b] < len(pools[b])]
        if not open_banks:
            break
        # Banks with a share come first; zero-share banks only top up once those have run out.
        candidates = [b for b in open_banks if shares.get(b, 0) > 0] or open_banks
        total = sum(shares.get(b, 0) for b in candidates) or 1
        # The bank furthest behind its (normalised) share goes next.
        bank = max(candidates, key=lambda b: (shares.get(b, 0) / total * k - taken[b], shares.get(b, 0)))
        picked.append(pools[bank][taken[bank]])
        taken[bank] += 1
    return picked
