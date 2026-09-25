"""Spaced repetition (Leitner boxes): words you know come back less and less often."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .answers import ALMOST, CORRECT, WRONG

READING = "reading"  # same as content.READING (no import: content imports answers)

MAX_BOX = 7
# Days until the next review, per box. Boxes 6 and 7 keep words that are really known from coming back
# ten times a year for ever: at a few thousand learned words, that is what makes a 25-minute day possible.
INTERVALS = {1: 1, 2: 3, 3: 7, 4: 16, 5: 35, 6: 75, 7: 150}
LEARNED_BOX = 3
LEECH_WRONGS = 4    # missed this often in all: a leech (it needs a different cue, not more of the same)
PARK_AFTER = 8      # missed this often: parked for PARK_DAYS (then 4 more misses park it again)
PARK_DAYS = 30


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
        if state["wrong"] >= PARK_AFTER + 4 * state.get("parks", 0):
            state["parks"] = state.get("parks", 0) + 1  # a break helps more than an eighth miss in a row
            days = PARK_DAYS
    state["due"] = (today + timedelta(days=days)).isoformat()


def is_leech(state: dict) -> bool:
    return state.get("wrong", 0) >= LEECH_WRONGS and state.get("box", 0) < LEARNED_BOX


def parked(state: dict, today: date) -> bool:
    """Parked after too many misses, and not back yet."""
    return bool(state.get("parks")) and state.get("box", 0) == 1 and (state.get("due") or "") > today.isoformat()


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


WARMUP_SHARE = 0.6       # of the day's minutes, the warm-up gets this much; the rest is reading
DEFAULT_SECONDS = 20.0   # per warm-up question, until the answer log knows this kid's pace


def session_minutes(settings: dict, data: dict, today: date) -> int:
    """Today's time budget: the kid's own setting, else config (school days / weekends)."""
    own = data.get("session_minutes")
    if isinstance(own, (int, float)) and not isinstance(own, bool) and own > 0:
        return int(own)
    budget = settings.get("session_minutes", {"weekday": 25, "weekend": 40})
    if isinstance(budget, (int, float)):
        return int(budget)
    return int(budget.get("weekend" if today.weekday() >= 5 else "weekday", 25))


def warmup_size(settings: dict, minutes: int, seconds_per_item: float = DEFAULT_SECONDS) -> int:
    """As many questions as fit in the warm-up's share of the day's minutes, at this kid's pace. Due words
    that don't fit wait for tomorrow (they keep first place); they are never doubled up."""
    fits = int(minutes * 60 * WARMUP_SHARE / max(float(seconds_per_item), 5.0))
    return max(int(settings["warmup_start"]), min(int(settings["warmup_max"]), fits))


def new_word_cap(settings: dict, size: int) -> int:
    cap = max(int(settings["min_new_words"]), round(size * float(settings["new_word_share"])))
    return min(cap, int(settings.get("new_word_max", 15)))


def new_words_today(settings: dict, size: int, days: dict, states: dict, today: date, due: int) -> tuple[int, str]:
    """How many new words today, and why if it isn't the usual number (docs/LEARNING_DESIGN.md 3.2):
    fewer while reviews go badly or many words keep slipping, a couple more while it goes very well, and
    none while a kid who skipped days catches up on a full session of due words."""
    top, bottom = int(settings.get("new_word_max", 15)), int(settings["min_new_words"])
    cap, reason = new_word_cap(settings, size), ""
    week_start = (today - timedelta(days=7)).isoformat()
    practised = [d for d, c in days.items() if week_start <= d < today.isoformat() and (c.get("warmups") or c.get("units"))]
    if len(practised) < 3 and due >= size:
        return 0, "catching up: reviews first today, new words once they're done"
    recent = [c for d, c in sorted(days.items()) if d < today.isoformat() and c.get("words")][-7:]
    answered = sum(c["words"] for c in recent)
    if answered >= 20:
        share = (sum(c.get("right", 0) for c in recent) + 0.5 * sum(c.get("almost", 0) for c in recent)) / answered
        if share < 0.7:
            cap, reason = cap - 2, "consolidating: fewer new words until the reviews go better"
        elif share > 0.9:
            cap, reason = cap + 2, "going well: a couple of extra new words"
    slipping = sum(1 for s in states.values() if is_leech(s) and not parked(s, today))
    if slipping > 10:
        cap, reason = cap - 3, f"{slipping} words keep slipping: fewer new ones until they stick"
    return max(bottom, min(cap, top)), reason


@dataclass
class Plan:
    reviews: list[str]
    new: list[str]
    practice: list[str]
    waiting: int = 0  # due words that didn't fit today: first in line tomorrow

    @property
    def total(self) -> int:
        return len(self.reviews) + len(self.new) + len(self.practice)


def reading_words_due(words: dict, queue: list[str], count: int) -> list[str]:
    """Key words of paragraphs already read, oldest first: new ones AND ones already known, because
    meeting a word again in a story is more repetition, and repetition is how words stick."""
    return [wid for wid in queue if wid in words][: max(count, 0)]


def plan_session(states: dict, words: dict, settings: dict, today: date, size: int, new_allowed: int,
                 allowed: set[str] | None = None, topics: tuple[str, ...] = ()) -> Plan:
    """Fill a warm-up of `size` words: due reviews come first (most overdue first); new words (up to
    `new_allowed`) only take the room the reviews leave, so the words already started never pile up
    unreviewed. Then extra practice on words already started (weakest, least recent first). If there is
    still room (early on, few words have been started), it is topped up with new words, so a warm-up is
    always full while the bank has words left."""
    t = today.isoformat()
    shares = settings["bank_shares"]
    due = [wid for wid, s in states.items()
           if wid in words and s.get("box", 0) >= 1 and s.get("due") and s["due"] <= t]
    due.sort(key=lambda wid: (states[wid]["due"], states[wid]["box"]))
    new = pick_new_words(states, words, min(max(new_allowed, 0), max(0, size - len(due))), shares, allowed, topics)
    reviews = due[: size - len(new)]
    taken = set(reviews)
    started = [wid for wid, s in states.items() if wid in words and s.get("box", 0) >= 1 and wid not in taken]
    started.sort(key=lambda wid: (states[wid].get("last") == t, states[wid]["box"], states[wid].get("last") or ""))
    practice = started[: size - len(new) - len(reviews)]
    room = size - len(new) - len(reviews) - len(practice)
    if room > 0:
        new = pick_new_words(states, words, len(new) + room, shares, allowed, topics)
    return Plan(reviews, new, practice, waiting=len(due) - len(reviews))


TOPIC_WINDOW = 500  # a favourite topic's word goes first among words within this many frequency ranks


def pick_new_words(states: dict, words: dict, count: int, shares: dict[str, float],
                   allowed: set[str] | None = None, topics: tuple[str, ...] = ()) -> list[str]:
    """Pick the most common unseen words, mixing the banks (daily, stem, admin) by their share.
    Words from the books never come this way: they join once their paragraph is read.
    allowed: only these ids (the kid's goal level, goals.py); topics: these go first among words about
    as common (within TOPIC_WINDOW ranks), so a favourite topic never pushes out much more common words."""
    pools: dict[str, list[str]] = {}
    order = (lambda w: (w.rank // TOPIC_WINDOW, w.topic not in topics, w.rank, w.id)) if topics \
        else (lambda w: (w.rank, w.id))
    for w in sorted(words.values(), key=order):
        if allowed is not None and w.id not in allowed:
            continue
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
