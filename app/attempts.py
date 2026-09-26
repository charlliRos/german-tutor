"""Every answer, kept for good: data/profiles/<name>_attempts.jsonl, one JSON object per line, only appended.

The boxes in the profile (vocab, verbs, genders) are the scheduler's working state. This log is the record:
rebuild() recomputes the boxes from it, so a damaged profile or a new scheduler doesn't cost a kid their
history. The first line is a "baseline": the boxes as they were when the log started (profiles from before
the log existed), then one "attempt" per answer.

Scores say who graded and how sure it is, so machine-checked and self-graded answers are never mixed up:
  dichotomous  {"correct": bool}                     right or wrong (der/die/das, grammar, "heard it")
  polytomous   {"points", "max", "label"}            correct 2 / almost 1 / wrong 0, dictation 0-100
  estimated    {"raw", "max", "confidence", "needs_review"}   the kid's own grade of a translation
  no_response  {"reason"}                            typed ?, skipped, or not a real try
These match the Open Learning Runtime's score kinds (docs/OLR_INTEGRATION.md); tools/export_olr.py
translates the log for it.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone

from . import srs
from .answers import ALMOST, CORRECT, WRONG

SCHEMA = 1
GRADER = "gtutor.answers/3"        # typed words, verb forms, gaps: app/answers.py (docs/TEXT_SCORER_SPEC.md)
DICTATION_GRADER = "gtutor.mark_words/1"
SPEECH_GRADER = "vosk-small-de"    # the offline speech check
UNCHECKED = "unchecked"            # speaking turn without a speech checker: counted, not verified
SELF = "self"                      # the kid's own grade
STORES = ("vocab", "verbs", "genders")  # the scheduler states rebuild() can recompute

POINTS = {CORRECT: 2, ALMOST: 1, WRONG: 0}
SELF_POINTS = {"needs work": 0, "mostly right": 1, "nailed it": 2}
SELF_CONFIDENCE = 0.5              # a kid grading themselves: useful, not certain

# What the question screen typed and decided, picked up by record() (the screens return only an outcome).
_pending: dict = {}


def version(*parts) -> str:
    """A short fingerprint of what an item asks and accepts. It changes when the wording or the answer does,
    so old answers stay tied to the version that was actually answered."""
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def word_version(word) -> str:
    return version(word.de, sorted(word.de_alt), list(word.en), word.pos)


def note(response: str = "", verdict: str = "", message: str = "", task: str = "", **extra) -> None:
    """Called by a question screen: what was typed and what the grader said."""
    _pending.clear()
    _pending.update(response=response, verdict=verdict, message=message, task=task, **extra)


def pending_task() -> str:
    """The task of the answer waiting to be recorded ("en2de", "gap", …)."""
    return _pending.get("task", "")


def speech_grader(ctx) -> str:
    audio = ctx.audio
    checks = getattr(audio, "can_check_speech", False) and ctx.settings.get("speech_check", True)
    return SPEECH_GRADER if checks else UNCHECKED


def graded(outcome: str) -> dict:
    return {"kind": "polytomous", "points": POINTS[outcome], "max": 2, "label": outcome}


def right_or_wrong(correct: bool) -> dict:
    return {"kind": "dichotomous", "correct": bool(correct)}


def self_graded(grade: str) -> dict:
    return {"kind": "estimated", "raw": SELF_POINTS.get(grade, 0), "max": 2, "confidence": SELF_CONFIDENCE,
            "needs_review": True, "label": grade}


def no_response(reason: str = "skipped") -> dict:
    return {"kind": "no_response", "reason": reason}


def _baseline(profile) -> dict:
    return {"v": SCHEMA, "type": "baseline", "at": _now(), "learner": profile.name,
            **{store: json.loads(json.dumps(profile.data.get(store, {}))) for store in STORES}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start(profile) -> None:
    """Begin the log with the baseline, before anything changes the boxes (called when an activity that
    changes them starts: a baseline written after the first answer would count that answer twice)."""
    if not profile.attempts_path.exists():
        profile.attempts_path.parent.mkdir(parents=True, exist_ok=True)
        with profile.attempts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_baseline(profile), ensure_ascii=False) + "\n")


def record_seed(profile, today: date, store: str, states: dict[str, dict]) -> None:
    """Boxes set without an answer each (the placement's "you most likely know these"): one event with the
    states, so rebuild() reproduces them. Only for items that had no box yet."""
    start(profile)
    event = {"v": SCHEMA, "type": "seed", "id": uuid.uuid4().hex, "at": _now(), "date": today.isoformat(),
             "learner": profile.name, "store": store, "states": states}
    with profile.attempts_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_nudge(profile, today: date, store: str, items: list[str], reason: str) -> None:
    """Items brought back without being asked (e.g. words from an exam text that was answered wrong): each gets
    srs.apply_practice(WRONG). One event, so rebuild() reproduces it."""
    start(profile)
    event = {"v": SCHEMA, "type": "nudge", "id": uuid.uuid4().hex, "at": _now(), "date": today.isoformat(),
             "learner": profile.name, "store": store, "items": items, "reason": reason}
    with profile.attempts_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record(profile, today: date, *, item: str, item_version: str, competency: str, subcompetency: str,
           context: str, score: dict, grader: str, schedule: str | None = None, store: str | None = None,
           counted: str | None = None, **extra) -> dict:
    """Append one answer. schedule/store/counted say what it did to the boxes, so rebuild() can redo it:
    schedule "result" / "practice" (srs.apply_result / apply_practice with `counted`), "practised"
    (srs.mark_practised), None (no effect: repeats, reading). Nothing is ever rewritten."""
    pending = dict(_pending)
    _pending.clear()
    event = {"v": SCHEMA, "type": "attempt", "id": uuid.uuid4().hex, "at": _now(), "date": today.isoformat(),
             "learner": profile.name, "item": item, "item_version": item_version,
             "competency": competency, "subcompetency": subcompetency, "context": context,
             "task": pending.pop("task", "") or extra.pop("task", ""),
             "response": pending.pop("response", ""), "score": score, "grader": grader}
    if pending.get("verdict") and pending["verdict"] != (counted or ""):
        event["machine_verdict"] = pending["verdict"]  # e.g. "my answer was right too" overrode it
    for key in ("message", "pasted"):
        if pending.get(key):
            event[key] = pending[key]
    event.update({k: v for k, v in extra.items() if v not in (None, "")})
    if schedule:
        event.update(schedule=schedule, store=store, counted=counted)
    start(profile)  # e.g. reading first: it doesn't change the boxes, so the baseline is still right
    with profile.attempts_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read(profile) -> list[dict]:
    """Every line of the log (a half-written last line, e.g. after a power cut, is skipped)."""
    if not profile.attempts_path.exists():
        return []
    events = []
    with profile.attempts_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    return events


def tail(profile, max_bytes: int = 300_000) -> list[dict]:
    """The last lines of the log (the whole log can be tens of MB after a year)."""
    path = profile.attempts_path
    if not path.exists():
        return []
    with path.open("rb") as f:
        size = f.seek(0, 2)
        f.seek(max(0, size - max_bytes))
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()[1:] if size > max_bytes else data.splitlines()  # the first may be cut
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def seconds_per_item(profile, recent: int = 200) -> float:
    """This kid's usual seconds per warm-up question: the median gap between answers in a warm-up
    (pauses over 2 minutes don't count), from the last `recent` answers. None known yet: the default."""
    from statistics import median
    events = [e for e in tail(profile) if e.get("type") == "attempt" and str(e.get("context", "")).startswith("warmup.")]
    gaps = []
    for before, after in zip(events, events[1:]):
        try:
            gap = (datetime.fromisoformat(after["at"]) - datetime.fromisoformat(before["at"])).total_seconds()
        except (KeyError, ValueError):
            continue
        if 2 <= gap <= 120:
            gaps.append(gap)
    gaps = gaps[-recent:]
    return float(median(gaps)) if len(gaps) >= 20 else srs.DEFAULT_SECONDS


def rebuild(events: list[dict]) -> dict[str, dict]:
    """The boxes (vocab, verbs, genders) recomputed from the log alone."""
    states: dict[str, dict] = {store: {} for store in STORES}
    for e in events:
        if e.get("type") == "baseline":
            for store in STORES:
                states[store] = json.loads(json.dumps(e.get(store, {})))
            continue
        if e.get("type") == "nudge" and e.get("store") in STORES:
            for item in e.get("items", []):
                srs.apply_practice(states[e["store"]].setdefault(item, srs.new_state()), WRONG,
                                   date.fromisoformat(e["date"]))
            continue
        if e.get("type") == "seed" and e.get("store") in STORES:
            for item, state in e.get("states", {}).items():
                states[e["store"]][item] = dict(state)
            continue
        if e.get("type") != "attempt" or not e.get("schedule") or e.get("store") not in STORES:
            continue
        state = states[e["store"]].setdefault(e["item"], srs.new_state())
        day = date.fromisoformat(e["date"])
        if e["schedule"] == "result":
            srs.apply_result(state, e["counted"], day)
        elif e["schedule"] == "practice":
            srs.apply_practice(state, e["counted"], day)
        elif e["schedule"] == "practised":
            srs.mark_practised(state, day)
    return states


# ----- competencies: what each kind of question practises (docs/OLR_INTEGRATION.md) -----

COMPETENCIES = {
    "vocabulary.production": "Recall the German word from its English meaning (typed)",
    "vocabulary.recognition": "Understand a German word (typed English meaning)",
    "vocabulary.in_context": "Use the right form of a word in a sentence (gap)",
    "listening.dictation": "Hear German and write it down exactly",
    "speaking.pronunciation": "Say a German word or text so a speech checker hears it",
    "grammar.noun_gender": "Know a noun's article: der, die or das",
    "grammar.case_articles": "Choose the article form the case needs (dem, einen, …)",
    "grammar.adjective_endings": "Choose the adjective ending (-e, -en, -er, -es, -em)",
    "grammar.word_order": "Put the words of a German sentence in order",
    "grammar.irregular_verbs": "Past tense and perfect of irregular verbs",
    "reading.translation_de_en": "Translate German text into English",
    "writing.translation_en_de": "Translate English text into German",
    "exam.reading": "Exam-style reading tasks (Goethe-Zertifikat format)",
    "exam.listening": "Exam-style listening tasks (Goethe-Zertifikat format)",
    "exam.writing": "Exam-style writing tasks, checked against the task's points",
    "exam.speaking": "Exam-style speaking tasks, checked for length and key words by the speech check",
}

WORD_TASKS = {"en2de": "vocabulary.production", "de2en": "vocabulary.recognition", "gap": "vocabulary.in_context",
              "dictation": "listening.dictation", "say": "speaking.pronunciation"}
GRAMMAR_KINDS = {"article": "grammar.case_articles", "ending": "grammar.adjective_endings",
                 "order": "grammar.word_order"}
TRANSLATION = {"de2en": "reading.translation_de_en", "en2de": "writing.translation_en_de"}


def word_subcompetency(word) -> str:
    """Word list and topic, e.g. "daily/family", "stem/physics"."""
    return f"{word.bank}/{word.topic or word.pos}"
