"""Exam practice: original practice exams in the format of the Goethe-Zertifikat (A2, B1), in content/exams/.

Reading and listening are marked by the app (multiple choice, richtig/falsch, ja/nein, matching); writing is
self-graded against the task's points, next to a model answer. Every answer goes to the answer log
(attempts.py); the best score per part is kept in the profile. Format: CONTENT_FORMAT.md, "Exam practice".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import CONTENT_DIR

EXAMS_DIR = CONTENT_DIR / "exams"
SKILLS = {"reading": "Lesen", "listening": "Hören", "writing": "Schreiben"}
ITEM_TYPES = ("mc", "tf", "yesno", "match")
PASS_SHARE = 0.6  # the Goethe exams are passed with 60% of the points in each module


@dataclass
class ExamText:
    id: str
    title: str = ""
    de: str = ""
    lines: list[dict] = field(default_factory=list)  # a conversation: [{"who", "de"}]

    @property
    def spoken(self) -> str:
        """What the voice reads (a conversation: the lines one after the other)."""
        return self.de or " ".join(line["de"] for line in self.lines)

    @property
    def transcript(self) -> str:
        return self.de or "\n".join(f"{line.get('who', '')}: {line['de']}" for line in self.lines)

    def label(self, width: int = 70) -> str:
        """A short name for a matching choice: its title, or the start of its text."""
        text = self.title or " ".join(self.spoken.split())
        return text if len(text) <= width else text[: width - 1] + "…"


@dataclass
class ExamItem:
    id: str
    type: str
    question: str
    answer: str
    options: dict[str, str] = field(default_factory=dict)
    text: str = ""
    explain_en: str = ""


@dataclass
class Part:
    id: str
    skill: str
    title_de: str
    instructions_en: str = ""
    minutes: int = 0
    texts: list[ExamText] = field(default_factory=list)
    items: list[ExamItem] = field(default_factory=list)
    plays: int = 2
    none_allowed: bool = False
    task_de: str = ""
    task_en: str = ""
    points: list[str] = field(default_factory=list)
    words: list[int] = field(default_factory=lambda: [0, 0])
    model_de: str = ""

    def text(self, text_id: str) -> ExamText | None:
        return next((t for t in self.texts if t.id == text_id), None)

    @property
    def max_points(self) -> int:
        return len(self.points) if self.skill == "writing" else len(self.items)


@dataclass
class Exam:
    id: str
    level: str
    style: str
    title: str
    parts: list[Part]
    about_en: str = ""
    official_practice: list[dict] = field(default_factory=list)

    def skill_parts(self, skill: str) -> list[Part]:
        return [p for p in self.parts if p.skill == skill]


def item_id(exam: Exam, part: Part, item: ExamItem | None = None) -> str:
    """Permanent id: <exam>.<part>.<item> (a writing task: <exam>.<part>)."""
    return f"{exam.id}.{part.id}" + (f".{item.id}" if item else "")


# ----- answers -----

def choices(item: ExamItem, part: Part) -> dict[str, str]:
    """Key to type -> what it means, in the order shown."""
    if item.type == "mc":
        return dict(item.options)
    if item.type == "tf":
        return {"r": "richtig", "f": "falsch"}
    if item.type == "yesno":
        return {"j": "ja", "n": "nein"}
    # A matching question that names a text (e.g. the conversation it's about) chooses among the others.
    out = {t.id: t.label() for t in part.texts if t.id != item.text}
    if part.none_allowed:
        out["x"] = "keine Anzeige / kein Text passt"
    return out


def canonical(item: ExamItem, key: str) -> str:
    """The answer a typed key stands for, in the form the content uses (r -> richtig, j -> ja)."""
    if item.type == "tf":
        return {"r": "richtig", "f": "falsch"}.get(key, key)
    if item.type == "yesno":
        return {"j": "ja", "n": "nein"}.get(key, key)
    return key


def is_right(item: ExamItem, key: str) -> bool:
    return canonical(item, key) == item.answer


def passed(score: int, total: int) -> bool:
    return total > 0 and score >= PASS_SHARE * total


# ----- loading and checking -----

def check_exam(raw: dict, name: str) -> list[str]:
    """What's wrong with an exam file ([] if nothing): used by the loader and tools/validate_content.py."""
    problems = []
    for key in ("id", "level", "style", "title", "parts"):
        if not raw.get(key):
            problems.append(f"{name}: missing {key}")
    part_ids = set()
    for p in raw.get("parts", []):
        where = f"{name} {p.get('id', '?')}"
        if p.get("id") in part_ids:
            problems.append(f"{where}: duplicate part id")
        part_ids.add(p.get("id"))
        if p.get("skill") not in SKILLS:
            problems.append(f"{where}: skill must be one of {', '.join(SKILLS)}")
            continue
        if p["skill"] == "writing":
            for key in ("task_de", "task_en", "points", "model_de"):
                if not p.get(key):
                    problems.append(f"{where}: a writing part needs {key}")
            words = p.get("words")
            if not (isinstance(words, list) and len(words) == 2 and all(isinstance(w, int) for w in words)):
                problems.append(f"{where}: words must be [min, target]")
            continue
        texts = {t.get("id") for t in p.get("texts", [])}
        for t in p.get("texts", []):
            if not t.get("de") and not all(isinstance(l, dict) and l.get("de") for l in t.get("lines") or [None]):
                problems.append(f"{where} text {t.get('id')}: needs de or lines")
        if not p.get("items"):
            problems.append(f"{where}: no items")
        item_ids = set()
        for it in p.get("items", []):
            iw = f"{where} item {it.get('id', '?')}"
            if it.get("id") in item_ids:
                problems.append(f"{iw}: duplicate item id")
            item_ids.add(it.get("id"))
            kind, answer = it.get("type"), it.get("answer")
            if kind not in ITEM_TYPES:
                problems.append(f"{iw}: type must be one of {', '.join(ITEM_TYPES)}")
                continue
            allowed = {"mc": set((it.get("options") or {}).keys()), "tf": {"richtig", "falsch"},
                       "yesno": {"ja", "nein"},
                       "match": (texts - {it.get("text")}) | ({"x"} if p.get("none_allowed") else set())}[kind]
            if kind == "mc" and set((it.get("options") or {}).keys()) != {"a", "b", "c"}:
                problems.append(f"{iw}: mc needs options a, b, c")
            if answer not in allowed:
                problems.append(f"{iw}: answer {answer!r} is not one of {sorted(allowed)}")
            if it.get("text") and it["text"] not in texts:
                problems.append(f"{iw}: text {it['text']!r} doesn't exist")
            if not it.get("question") or not it.get("explain_en"):
                problems.append(f"{iw}: needs question and explain_en")
    return problems


def _exam(raw: dict) -> Exam:
    parts = []
    for p in raw["parts"]:
        parts.append(Part(
            id=p["id"], skill=p["skill"], title_de=p.get("title_de", p["id"]),
            instructions_en=p.get("instructions_en", ""), minutes=int(p.get("minutes", 0) or 0),
            texts=[ExamText(id=t["id"], title=t.get("title", ""), de=t.get("de", ""), lines=t.get("lines") or [])
                   for t in p.get("texts", [])],
            items=[ExamItem(id=str(i["id"]), type=i["type"], question=i["question"], answer=i["answer"],
                            options=i.get("options") or {}, text=i.get("text", ""), explain_en=i.get("explain_en", ""))
                   for i in p.get("items", [])],
            plays=int(p.get("plays", 2) or 2), none_allowed=bool(p.get("none_allowed")),
            task_de=p.get("task_de", ""), task_en=p.get("task_en", ""), points=list(p.get("points", [])),
            words=list(p.get("words", [0, 0])), model_de=p.get("model_de", "")))
    return Exam(id=raw["id"], level=raw["level"], style=raw["style"], title=raw["title"], parts=parts,
                about_en=raw.get("about_en", ""), official_practice=list(raw.get("official_practice", [])))


def load_exams(exams_dir: Path = EXAMS_DIR) -> tuple[list[Exam], list[str]]:
    """All exams that load cleanly, by level then id, and the problems of the ones that don't."""
    exams, problems = [], []
    for path in sorted(exams_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: cannot read ({exc})")
            continue
        found = check_exam(raw, path.name)
        if found:
            problems.extend(found)
            continue
        exams.append(_exam(raw))
    return sorted(exams, key=lambda e: (e.level, e.id)), problems
