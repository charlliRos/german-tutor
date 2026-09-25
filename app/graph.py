"""The skill graph (docs/LEARNING_DESIGN.md section 5): what a kid knows, what's next, and why they're stuck.

Nodes: word sets (everyday words by level and topic; STEM and official words by topic), grammar points
(content/graph/grammar.json, with prerequisites) and exam task types (the parts of the practice exams).
Everything is worked out from the boxes and the answer log; nothing is stored, so nothing can drift.

Mastery per node, from 0 to 1:
- word sets: the mean strength of their words (box 3 = 0.6 … box 6 = 1.0), halved for a word overdue by more
  than twice its interval, and capped for a word that keeps slipping;
- grammar points and exam task types: accuracy over their answers, the recent ones counting most
  (half-life HALF_LIFE answers). Self-graded answers are shown apart ("claimed"), never mixed in.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import srs
from .config import CONTENT_DIR

GRAMMAR_FILE = CONTENT_DIR / "graph" / "grammar.json"
STRENGTH = {0: 0.0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.75, 5: 0.9, 6: 1.0, 7: 1.0}
LEECH_CAP = 0.35
HALF_LIFE = 20       # answers: an answer this many answers ago counts half
SOLID, RUSTY = 0.8, 0.65
PRACTISING_AFTER, SOLID_AFTER = 10, 20   # answers before a node counts as being practised / can be solid
LEVELS = ("A1", "A2", "B1", "B2")
WEIGHTS = {"vocab": 0.4, "grammar": 0.3, "exam": 0.2, "text": 0.1}  # readiness for a level


@dataclass
class Node:
    id: str
    kind: str                 # vocab, grammar, exam
    level: str
    title: str
    requires: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)       # word ids (vocab nodes)
    scored_from: list[dict] = field(default_factory=list)  # grammar / exam: which answers measure it
    explain_en: str = ""


@dataclass
class NodeState:
    mastery: float = 0.0
    answers: int = 0
    coverage: float = 0.0     # vocab: words started / words
    claimed: float | None = None  # self-graded, shown apart
    state: str = "open"       # locked, open, practising, solid, rusty
    leeches: list[str] = field(default_factory=list)


# ----- building the graph -----

def load_grammar(path: Path = GRAMMAR_FILE) -> list[Node]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Node(id=n["id"], kind="grammar", level=n.get("level", ""), title=n.get("title_en", n["id"]),
                 requires=list(n.get("requires", [])), scored_from=list(n.get("scored_from", [])),
                 explain_en=n.get("explain_en", "")) for n in raw.get("nodes", [])]


def build(content, exams: list = (), grammar: list[Node] | None = None) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for w in content.words.values():
        if w.bank == "reading":
            continue
        if w.bank == "daily":
            nid, level, title = f"vocab:{w.level or 'A1'}/{w.topic or 'other'}", w.level or "A1", f"{w.topic} words ({w.level})"
        else:
            nid, level, title = f"vocab:{w.bank}/{w.topic or 'other'}", "B2", f"{w.bank} words: {w.topic}"
        nodes.setdefault(nid, Node(nid, "vocab", level, title)).items.append(w.id)
    for exam in exams:
        for part in exam.parts:
            nid = f"exam:{exam.level}.{part.id}"
            nodes[nid] = Node(nid, "exam", exam.level, f"{exam.level} {part.title_de}", scored_from=[
                {"competency": f"exam.{part.skill}", "subcompetency": f"{exam.level}/{part.id}"}])
    for node in load_grammar() if grammar is None else grammar:
        nodes[node.id] = node
    return nodes


# ----- mastery -----

def item_strength(state: dict, today: date) -> float:
    box = state.get("box", 0)
    strength = STRENGTH.get(box, 1.0)
    due = state.get("due")
    if due and box >= 1:
        overdue = (today - date.fromisoformat(due)).days
        if overdue > 2 * srs.INTERVALS.get(box, 1):
            strength /= 2
    if srs.is_leech(state):
        strength = min(strength, LEECH_CAP)
    return strength


def _matches(event: dict, rules: list[dict]) -> bool:
    return any(event.get("competency") == r.get("competency")
               and fnmatch.fnmatch(str(event.get("subcompetency", "")), r.get("subcompetency", "*"))
               for r in rules)


def _weighted(values: list[float]) -> float:
    """Newest last; each answer HALF_LIFE answers older counts half."""
    weights = [0.5 ** ((len(values) - 1 - i) / HALF_LIFE) for i in range(len(values))]
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def _score_value(score: dict) -> float | None:
    kind = score.get("kind")
    if kind == "dichotomous":
        return 1.0 if score.get("correct") else 0.0
    if kind == "polytomous":
        return score.get("points", 0) / max(score.get("max", 1), 1)
    if kind == "no_response":
        return 0.0  # for mastery; the kid's own accuracy doesn't count it
    return None


def mastery(nodes: dict[str, Node], vocab: dict, events: list[dict], today: date) -> dict[str, NodeState]:
    out: dict[str, NodeState] = {}
    answers = [e for e in events if e.get("type") == "attempt"]
    for nid, node in nodes.items():
        st = NodeState()
        if node.kind == "vocab":
            states = [vocab.get(wid, {}) for wid in node.items]
            started = [s for s in states if s.get("box", 0) >= 1]
            st.mastery = sum(item_strength(s, today) for s in states) / len(states) if states else 0.0
            st.coverage = len(started) / len(states) if states else 0.0
            st.answers = sum(s.get("seen", 0) for s in started)
            st.leeches = [wid for wid in node.items if srs.is_leech(vocab.get(wid, {}))]
            learned = sum(1 for s in started if s.get("box", 0) >= srs.LEARNED_BOX)
            if st.mastery >= SOLID * 0.9 and st.coverage >= 0.9:
                st.state = "solid"
            elif started and learned >= 0.6 * len(started) and st.mastery < RUSTY * st.coverage:
                st.state = "rusty"   # mostly learned once, now fading
            elif started:
                st.state = "practising"
        else:
            mine = [e for e in answers if node.scored_from and _matches(e, node.scored_from)]
            machine = [v for e in mine if (v := _score_value(e.get("score", {}))) is not None]
            claimed = [e["score"]["raw"] / max(e["score"].get("max", 1), 1) for e in mine
                       if e.get("score", {}).get("kind") == "estimated"]
            st.answers = len(machine)
            st.mastery = _weighted(machine) if machine else 0.0
            st.claimed = sum(claimed) / len(claimed) if claimed else None
            if st.answers >= SOLID_AFTER and st.mastery >= SOLID:
                st.state = "solid"
            elif st.answers >= SOLID_AFTER and _weighted(machine[: len(machine) // 2] or machine) >= SOLID > st.mastery:
                st.state = "rusty"   # was solid, slipping lately
            elif st.answers >= PRACTISING_AFTER:
                st.state = "practising"
        out[nid] = st
    for nid, node in nodes.items():  # locked: a prerequisite isn't solid yet (and this node isn't either)
        if out[nid].state in ("open", "practising") and any(
                out.get(r) and out[r].state not in ("solid", "rusty") for r in node.requires):
            out[nid].state = "locked" if out[nid].answers == 0 else out[nid].state
    return out


def everyday(node: Node) -> bool:
    """An everyday-word set (vocab:A2/food), not STEM or official words (they don't count for a level)."""
    return node.id.split(":", 1)[1].split("/", 1)[0] in LEVELS + ("C1",)


def readiness(nodes: dict[str, Node], states: dict[str, NodeState], level: str) -> dict[str, float | None]:
    """Readiness for a level (0–1) and its parts: words, grammar, exam tasks. Everything at or below the level
    counts. A part with no data yet is None and left out of the total (never counted as weak)."""
    upto = LEVELS[: LEVELS.index(level) + 1] if level in LEVELS else LEVELS
    parts: dict[str, float | None] = {}
    for kind in ("vocab", "grammar", "exam"):
        chosen = [(n, states[n.id]) for n in nodes.values() if n.kind == kind and n.level in upto
                  and (kind != "vocab" or everyday(n))]
        if kind == "vocab":
            size = sum(len(n.items) for n, _ in chosen)
            parts[kind] = sum(s.mastery * len(n.items) for n, s in chosen) / size if size else None
        else:
            known = [s.mastery for n, s in chosen if s.answers]
            parts[kind] = sum(known) / len(known) if known else None
    have = {k: v for k, v in parts.items() if v is not None}
    total = sum(WEIGHTS[k] * v for k, v in have.items()) / sum(WEIGHTS[k] for k in have) if have else 0.0
    return {"total": total, **parts}


def frontier(nodes: dict[str, Node], states: dict[str, NodeState], level: str) -> list[str]:
    """Grammar points to work on next: open or being practised, prerequisites solid, up to one level above the
    goal; weakest first."""
    top = LEVELS.index(level) + 2 if level in LEVELS else len(LEVELS)
    ready = [n for n in nodes.values() if n.kind == "grammar" and n.level in LEVELS[:top]
             and states[n.id].state in ("open", "practising", "rusty")
             and all(states.get(r) and states[r].state in ("solid", "rusty") for r in n.requires)]
    return [n.id for n in sorted(ready, key=lambda n: (LEVELS.index(n.level), states[n.id].mastery))]


# ----- why is my kid stuck -----

def weakest_prerequisite(nodes: dict[str, Node], states: dict[str, NodeState], nid: str) -> str | None:
    """The prerequisite chain's weakest link that isn't solid (walking down the requires edges)."""
    seen, stack, weak = set(), list(nodes[nid].requires), []
    while stack:
        r = stack.pop()
        if r in seen or r not in nodes:
            continue
        seen.add(r)
        if states[r].state not in ("solid",):
            weak.append(r)
        stack.extend(nodes[r].requires)
    return min(weak, key=lambda r: states[r].mastery) if weak else None


def stuck(nodes: dict[str, Node], states: dict[str, NodeState], profile_data: dict, today: date) -> list[dict]:
    """One block per stuck node: practised a lot but still weak (or fading), with the likely causes."""
    blocks = []
    for nid, node in nodes.items():
        st = states[nid]
        weak_after_practice = st.state == "practising" and st.answers >= SOLID_AFTER and st.mastery < 0.6
        if not (weak_after_practice or st.state == "rusty") or node.kind == "vocab":
            continue
        prereq = weakest_prerequisite(nodes, states, nid)
        blocks.append({"node": node, "state": st, "because": prereq and (nodes[prereq], states[prereq])})
    days = profile_data.get("days", {})
    week = [c for d, c in days.items() if (today - timedelta(days=7)).isoformat() <= d < today.isoformat()
            and (c.get("warmups") or c.get("units"))]
    leechy = sorted(((n, states[n.id]) for n in nodes.values() if n.kind == "vocab" and states[n.id].leeches),
                    key=lambda ns: -len(ns[1].leeches))[:2]
    return [{**b, "leeches": leechy, "days_a_week": len(week),
             "minutes": round(sum(c.get("seconds", 0) for c in week) / 60 / max(len(week), 1))} for b in blocks]


def suggestion(block: dict) -> str:
    if block["because"]:
        return f"practise \"{block['because'][0].title}\" first (the app puts it first)"
    if block["days_a_week"] < 3:
        return "short sessions on more days work better than a long one: try 4 days a week"
    if block["leeches"]:
        return "ask them about the memory hooks they wrote for their trickiest words"
    return "a 10-minute Saturday session with just this topic"
