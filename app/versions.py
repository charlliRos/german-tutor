"""Item versions: which edits to the content changed an answer, which changed the wording, which only the
looks. Kept in content/item_versions.json, one line per item, updated with `python tools/item_versions.py`.

Every word, verb form and book paragraph has a permanent id. Content can be fixed, but a learner's old
answers must stay tied to the version they actually answered, so each edit is sorted into a tier:

  answer        what counts as right changed (German word, accepted forms, meanings; verb forms; the German
                text of a paragraph). Old results don't describe the new item.
  wording       what the learner is shown changed, the answer didn't (a verb's English; a paragraph's
                reference translation).
  presentation  explanations, examples, notes, key-word lists. Old results still fit.

This follows the Open Learning Runtime's edit tiers (docs/OLR_INTEGRATION.md). Ids are never reused: a
removed item is marked retired, and a paragraph whose text changed completely is refused, because that
means paragraphs were renumbered and every scheduled look back would point at the wrong text.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from datetime import date
from pathlib import Path

from .config import BOOKS_DIR, CONTENT_DIR, VERBS_DIR, VOCAB_DIR
from .content import vocab_files

VERSIONS_FILE = CONTENT_DIR / "item_versions.json"
TIERS = ("answer", "wording", "presentation")  # most serious first
SAME_PARAGRAPH = 0.6  # a paragraph's opening less similar than this to the recorded one: renumbered?
OPENING = 80          # characters of a paragraph's German kept, to recognise it after an edit

WORD_FIELDS = {"answer": ("de", "de_alt", "en", "pos"),
               "wording": (),
               "presentation": ("plural", "note", "example_de", "example_en", "topic", "level", "rank")}
UNIT_FIELDS = {"answer": ("de",), "wording": ("en",), "presentation": ("explain_en", "words", "sentences")}


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:10]


def _fingerprint(raw: dict, fields: dict[str, tuple]) -> dict[str, str]:
    return {tier: _hash([raw.get(f) for f in names]) for tier, names in fields.items()}


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def current_items(vocab_dir: Path = VOCAB_DIR, books_dir: Path = BOOKS_DIR, verbs_dir: Path = VERBS_DIR,
                  exams_dir: Path = CONTENT_DIR / "exams") -> dict:
    """{item id: {"kind", tier hashes…, "text"?}} for everything in content/ right now (from the raw files)."""
    items = {}
    for path in vocab_files(vocab_dir):
        for w in _load(path).get("words", []):
            if w.get("id"):
                items[w["id"]] = {"kind": "word", **_fingerprint(w, WORD_FIELDS)}
    for path in sorted(verbs_dir.glob("*.json")):
        for v in _load(path).get("verbs", []):
            for kind in ("past", "perfect"):
                items[f"{v['inf']}|{kind}"] = {"kind": "verb", "answer": _hash([v.get(kind), v.get("alt")]),
                                               "wording": _hash(v.get("en")), "presentation": _hash(None)}
    for path in sorted(books_dir.glob("*.json")):
        book = _load(path)
        for u in book.get("units", []):
            if u.get("type") == "summary":
                continue
            items[f"{book['id']}#{u['n']}"] = {"kind": "paragraph", **_fingerprint(u, UNIT_FIELDS),
                                              "opening": u.get("de", "")[:OPENING]}
    for path in sorted(exams_dir.glob("*.json")):
        exam = _load(path)
        for part in exam.get("parts", []):
            texts = {t.get("id"): t for t in part.get("texts", [])}
            if part.get("skill") == "speaking":
                for t in part.get("tasks", []):
                    items[f"{exam['id']}.{part['id']}.{t.get('id')}"] = {
                        "kind": "exam", "answer": _hash(t.get("keywords")),
                        "wording": _hash([t.get("prompt_de"), t.get("partner_de"), t.get("card")]),
                        "presentation": _hash([t.get("prompt_en"), t.get("model_de")])}
                continue
            if part.get("skill") == "writing":
                items[f"{exam['id']}.{part['id']}"] = {
                    "kind": "exam", "answer": _hash(part.get("points")), "wording": _hash(part.get("task_de")),
                    "presentation": _hash([part.get("task_en"), part.get("model_de")])}
                continue
            for it in part.get("items", []):
                items[f"{exam['id']}.{part['id']}.{it.get('id')}"] = {
                    "kind": "exam", "answer": _hash([it.get("answer"), it.get("options")]),
                    "wording": _hash([it.get("question"), texts.get(it.get("text")) or list(texts.values())]),
                    "presentation": _hash(it.get("explain_en"))}
    return items


def load_versions(path: Path = VERSIONS_FILE) -> dict:
    """{item id: {"kind", "v", tier hashes…, "retired"?, "history"?}} (empty if there's no file yet)."""
    if not path.exists():
        return {}
    items = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line.startswith('"'):
                key, _, value = line.partition(": ")
                items[json.loads(key)] = json.loads(value)
    return items


def compare(recorded: dict, current: dict) -> tuple[list, list]:
    """(changes, refusals). changes: (id, tier or "new" / "retired"). refusals: why the content can't be
    accepted (a paragraph that is a different paragraph now: renumbered)."""
    changes, refusals = [], []
    for item_id, now in current.items():
        before = recorded.get(item_id)
        if before is None or before.get("retired"):
            changes.append((item_id, "new"))
            continue
        tier = next((t for t in TIERS if before.get(t) != now[t]), None)
        if tier:
            changes.append((item_id, tier))
            if now["kind"] == "paragraph" and tier == "answer" and difflib.SequenceMatcher(
                    a=before.get("opening", ""), b=now["opening"], autojunk=False).ratio() < SAME_PARAGRAPH:
                refusals.append(f"{item_id}: the German text is a different paragraph now. Paragraphs are never "
                                "renumbered (look backs are scheduled by number): add new paragraphs at the end "
                                "of a book, or in a new book.")
    for item_id, before in recorded.items():
        if item_id not in current and not before.get("retired"):
            changes.append((item_id, "retired"))
    return changes, refusals


def update(recorded: dict, current: dict, changes: list, today: date) -> dict:
    """The new version records after `changes` (from compare)."""
    out = {k: dict(v) for k, v in recorded.items()}
    for item_id, what in changes:
        if what == "retired":
            out[item_id]["retired"] = today.isoformat()
            continue
        now = dict(current[item_id])
        if what == "new":
            out[item_id] = {**now, "v": 1, "since": today.isoformat()}
            continue
        entry = out[item_id]
        entry.update(now, v=entry.get("v", 1) + 1)
        entry.setdefault("history", []).append({"v": entry["v"], "date": today.isoformat(), "tier": what})
    return out


def save_versions(items: dict, path: Path = VERSIONS_FILE) -> None:
    """One item per line, sorted, so a content edit shows up as a one-line change in git."""
    lines = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(items[k], ensure_ascii=False, sort_keys=True)}"
             for k in sorted(items)]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    tmp.replace(path)
