"""Answers the kids said were right ("my answer was right too"), collected from their answer logs, so a parent
(or Astra) can review them. An accepted answer goes into the word bank, so the checker knows it from then on,
for every kid. Reviewed claims are remembered in data/claims_reviewed.json and not asked again.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import attempts
from .answers import normalize
from .config import PROFILES_DIR, VERBS_DIR, VOCAB_DIR
from .content import vocab_files

REVIEWED_FILE = PROFILES_DIR.parent / "claims_reviewed.json"


@dataclass
class Claim:
    item: str            # word id, "inf|past" for a verb form, "<word>|grammar.<kind>" for grammar
    task: str            # en2de, de2en, gap, past, perfect, article, ending, order …
    response: str        # what was typed (the first spelling seen)
    kids: set[str] = field(default_factory=set)
    count: int = 0
    last: str = ""

    @property
    def key(self) -> str:
        return f"{self.item}|{self.task}|{normalize(self.response)}"

    @property
    def kind(self) -> str:
        return "grammar" if "|grammar." in self.item else "verb" if "|" in self.item else "word"

    @property
    def can_add(self) -> bool:
        """Can an accepted answer be added to the content? Words (typed either way) and verb forms can;
        grammar questions are made fresh from sentences, and book key words come from the books."""
        return (self.kind == "word" and self.task in ("en2de", "de2en") and not self.item.startswith("reading.")) \
            or self.kind == "verb"


def _is_claim(e: dict) -> bool:
    if e.get("type") != "attempt" or not e.get("response"):
        return False
    if e.get("claimed_correct"):
        return True
    score = e.get("score", {})
    right = score.get("correct") is True or score.get("label") == "correct"
    return e.get("machine_verdict") in ("wrong", "almost") and right


def collect(profiles, reviewed: dict[str, str] | None = None) -> list[Claim]:
    """Claims not reviewed yet, the most frequent first."""
    reviewed = load_reviewed() if reviewed is None else reviewed
    found: dict[str, Claim] = {}
    for profile in profiles:
        for e in attempts.read(profile):
            if not _is_claim(e):
                continue
            claim = Claim(e["item"], e.get("task", ""), e["response"].strip())
            if claim.key in reviewed:
                continue
            known = found.setdefault(claim.key, claim)
            known.kids.add(profile.name)
            known.count += 1
            known.last = max(known.last, e.get("date", ""))
    return sorted(found.values(), key=lambda c: (-c.count, c.item))


def load_reviewed(path: Path | None = None) -> dict[str, str]:
    try:
        return json.loads((path or REVIEWED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_reviewed(reviewed: dict[str, str], path: Path | None = None) -> None:
    path = path or REVIEWED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=1), encoding="utf-8")


def accept(claim: Claim, vocab_dir: Path | None = None, verbs_dir: Path | None = None) -> bool:
    """Add the claimed answer to the content. True if it was added (or was there already)."""
    vocab_dir, verbs_dir = vocab_dir or VOCAB_DIR, verbs_dir or VERBS_DIR
    if claim.kind == "word":
        field_name = "de_alt" if claim.task == "en2de" else "en"
        for path in vocab_files(vocab_dir):
            data = json.loads(path.read_text(encoding="utf-8"))
            for w in data.get("words", []):
                if w.get("id") == claim.item:
                    values = w.setdefault(field_name, [])
                    if normalize(claim.response) not in {normalize(v) for v in values} | {normalize(w.get("de", ""))}:
                        values.append(claim.response)
                        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    return True
        return False
    if claim.kind == "verb":
        inf = claim.item.split("|")[0]
        for path in sorted(verbs_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for v in data.get("verbs", []):
                if v.get("inf") == inf:
                    alt = v.setdefault("alt", [])
                    if normalize(claim.response) not in {normalize(a) for a in alt}:
                        alt.append(claim.response)
                        _write_verbs(path, data)
                    return True
        return False
    return False


def _write_verbs(path: Path, data: dict) -> None:
    """The verb file keeps one verb per line."""
    head = {k: v for k, v in data.items() if k != "verbs"}
    lines = ["{"] + [f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},' for k, v in head.items()]
    lines.append('  "verbs": [')
    verbs = [f"    {json.dumps(v, ensure_ascii=False)}" for v in data["verbs"]]
    lines.append(",\n".join(verbs))
    lines += ["  ]", "}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
