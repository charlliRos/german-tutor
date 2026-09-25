"""Export the words, verbs and books (and, if asked, answer logs) for the Open Learning Runtime.

    python tools/export_olr.py                     # content only, into export/olr/
    python tools/export_olr.py --attempts Anna     # also Anna's answer log (her typed answers: private)

THROWAWAY FORMAT (format_version 0). OLR's content package (signed manifest, digest, scope certificate) is
designed but not built yet, so this writes our best reading of its design as plain files, to be rewritten
when their package format exists. What does not change: the item ids, versions, competencies, provenance
and the answer log it is made from (docs/OLR_INTEGRATION.md).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import attempts  # noqa: E402
from app.config import BOOKS_DIR, PROFILES_DIR, ROOT  # noqa: E402
from app.content import READING, load_content  # noqa: E402
from app.exams import canonical, choices, item_id, load_exams  # noqa: E402
from app.genders import eligible, split  # noqa: E402
from app.profile import Profile  # noqa: E402
from app.versions import load_versions  # noqa: E402

FORMAT_VERSION = 0
LIFE_PLUS_70 = ["DE", "AT", "CH", "EU", "ID"]  # author died + 70 years (Indonesia: UU 28/2014, art. 58)


def _text(value: str, lang: str) -> dict:
    return {"block": "text", "lang": lang, "value": value}


def word_items(content, versions: dict) -> list[dict]:
    """Two typed questions per word (English → German, German → English), plus der/die/das for nouns."""
    items = []
    for w in content.words.values():
        if w.bank == READING:
            continue  # key words of the books: exported with their paragraph
        common = {"source_item": w.id, "version": versions.get(w.id, {}).get("v", 1),
                  "subcompetency": attempts.word_subcompetency(w), "level": w.level, "frequency_rank": w.rank}
        explanation = [_text(w.example_de, "de"), _text(w.example_en, "en")] if w.example_de else []
        if w.note:
            explanation.append(_text(w.note, "en"))
        items.append({"id": f"{w.id}.en2de", "competency": "vocabulary.production", **common, "input": "text",
                      "prompt": [_text(", ".join(w.en[:2]), "en")],
                      "key": {"scoring": f"{attempts.GRADER}#german", "accept": [w.de, *w.de_alt], "pos": w.pos},
                      "explanation": explanation})
        items.append({"id": f"{w.id}.de2en", "competency": "vocabulary.recognition", **common, "input": "text",
                      "prompt": [_text(w.de, "de")],
                      "key": {"scoring": f"{attempts.GRADER}#english", "accept": list(w.en)},
                      "explanation": explanation})
        if eligible(w):
            article, noun = split(w.de)
            items.append({"id": f"{w.id}.gender", "competency": "grammar.noun_gender", **common,
                          "input": "choice_single", "prompt": [_text(noun, "de")],
                          "options": [{"id": a, "label": a} for a in ("der", "die", "das")],
                          "key": {"scoring": "exact_option", "option": article}})
    return items


def verb_items(content, versions: dict) -> list[dict]:
    items = []
    for verb in content.verbs.values():
        for kind in ("past", "perfect"):
            key = f"{verb.inf}|{kind}"
            items.append({"id": key, "version": versions.get(key, {}).get("v", 1),
                          "competency": "grammar.irregular_verbs", "subcompetency": kind, "input": "text",
                          "prompt": [_text(verb.inf, "de"), _text(verb.en, "en")],
                          "key": {"scoring": "gtutor.verbs/1", "accept": [verb.past if kind == "past" else verb.perfect],
                                  "also_standard": [a for a in verb.alt if (" " in a) == (kind == "perfect")]}})
    return items


def exam_items(versions: dict) -> list[dict]:
    """Practice exams: every reading/listening question is a choice_single item for OLR's built exact_option
    scorer; listening recordings are exported as scripts (speaking them needs OLR's open audio.tts)."""
    items = []
    for exam in load_exams()[0]:
        for part in exam.parts:
            common = {"competency": f"exam.{part.skill}", "subcompetency": f"{exam.level}/{part.id}",
                      "level": exam.level, "exam_style": exam.style}
            if part.skill == "writing":
                iid = item_id(exam, part)
                items.append({"id": iid, "version": versions.get(iid, {}).get("v", 1), **common, "input": "text",
                              "prompt": [_text(part.task_de, "de"), _text(part.task_en, "en")],
                              "points": part.points, "words": part.words, "model_answer": part.model_de,
                              "score_kind": "estimated", "grader": attempts.SELF})
                continue
            block = "audio_script" if part.skill == "listening" else "text"
            for item in part.items:
                iid = item_id(exam, part, item)
                texts = [part.text(item.text)] if item.text else part.texts
                prompt = [{"block": block, "lang": "de", "value": t.transcript} for t in texts if t]
                prompt.append(_text(item.question, "de"))
                options = [{"id": canonical(item, k), "label": v} for k, v in choices(item, part).items()]
                items.append({"id": iid, "version": versions.get(iid, {}).get("v", 1), **common,
                              "input": "choice_single", "prompt": prompt, "options": options,
                              "key": {"scoring": "exact_option", "option": item.answer},
                              "explanation": [_text(item.explain_en, "en")]})
    return items


def rights(raw: dict, today: date) -> dict:
    """Why a book's German text is public domain, worked out from the author's death and first publication."""
    died, year = raw.get("author_died"), raw.get("year")
    out = {"author": raw.get("author"), "author_died": died, "first_published": year,
           "source_edition": raw.get("source"), "orthography": raw.get("orthography", ""),
           "translations": "English translations, explanations, key words and summaries were written for "
                           "this app (their licence is not chosen yet)"}
    out["computed_for"] = {"life_plus_70": LIFE_PLUS_70, "publication_plus_95": ["US"],
                           "note": "Which rule applies depends on where the package is distributed, not where "
                                   "the author lived. Other countries were not checked."}
    if isinstance(died, int):
        out.update(basis="author's life + 70 years", public_domain_from=f"{died + 71}-01-01",
                   life_plus_70_jurisdictions=LIFE_PLUS_70, public_domain_now=today.year >= died + 71)
    if isinstance(year, int):
        # US: works published 1929 or later are protected 95 years from publication (not verified per work).
        out.update(us_public_domain_from=f"{year + 96}-01-01" if year >= 1929 else "before 1929 publication",
                   us_public_domain_now=year < 1929 or today.year >= year + 96)
    return out


def books(content, versions: dict, today: date) -> list[dict]:
    loaded = {b.id: b for b in content.books}
    out = []
    for path in sorted(BOOKS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        book = loaded.get(raw.get("id"))
        if book is None:
            continue
        units = []
        for u in book.units:
            if u.kind != "text":
                units.append({"kind": "summary", "n": u.n, "en": u.en})
                continue
            pid = f"{book.id}#{u.n}"
            units.append({"kind": "paragraph", "id": pid, "n": u.n, "part": u.part,
                          "version": versions.get(pid, {}).get("v", 1), "de": u.de, "en": u.en,
                          "explain_en": u.explain_en, "key_words": u.words,
                          "tasks": [{"id": f"{pid}.{d}", "competency": attempts.TRANSLATION[d], "input": "text",
                                     "score_kind": "estimated", "grader": attempts.SELF} for d in ("de2en", "en2de")]})
        out.append({"id": book.id, "title": book.title, "level": book.level, "intro_en": book.intro_en,
                    "rights": rights(raw, today), "units": units})
    return out


SCORE_NAMES = {"dichotomous": "Dichotomous", "polytomous": "Polytomous", "estimated": "Estimated"}
UNMAPPED_NO_RESPONSE = ("OLR's score union has no 'did not answer' state for these items (Dichotomous has only "
                        "correct: bool; our typed and self-graded items aren't option-based, so Polytomous's "
                        "chosen: None doesn't fit either). Left unmapped rather than turned into 'wrong': "
                        "see OLR's open question NQ-K2-UNANSWERED-VS-WRONG.")


def export_attempt(e: dict) -> dict:
    """One answer-log line in OLR's attempt-event shape: an append-only event with a closed score union."""
    score = dict(e["score"])
    kind = score.pop("kind")
    if kind == "no_response":
        mapped, unmapped = None, {"kind": "no_response", **score, "why": UNMAPPED_NO_RESPONSE}
    else:
        if kind == "estimated":
            score["grader"] = e["grader"]
        mapped, unmapped = {SCORE_NAMES[kind]: score}, None
    item = e["item"]
    if e.get("task") and "#" not in item and "|" not in item:
        item = f"{item}.{e['task']}"  # word answers: the question, not just the word
    return {"event_id": e["id"], "at": e["at"], "learner": e["learner"], "item": item,
            "item_version": e["item_version"], "competency": e["competency"], "subcompetency": e["subcompetency"],
            "response": e.get("response", ""), "score": mapped, "grader": e["grader"],
            **({"unmapped": unmapped} if unmapped else {}),
            **({"machine_verdict": e["machine_verdict"]} if e.get("machine_verdict") else {}),
            **({"claimed_correct": True} if e.get("claimed_correct") else {})}


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return ""


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "export" / "olr"), help="folder to write (default export/olr)")
    parser.add_argument("--attempts", nargs="*", default=[], metavar="NAME",
                        help="also export these kids' answer logs (contains what they typed)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    today = date.today()
    content, versions = load_content(), load_versions()
    items = word_items(content, versions) + verb_items(content, versions) + exam_items(versions)
    book_rows = books(content, versions, today)
    write_jsonl(out / "items.jsonl", items)
    write_jsonl(out / "books.jsonl", book_rows)
    (out / "competencies.json").write_text(json.dumps(
        [{"id": cid, "description": text} for cid, text in attempts.COMPETENCIES.items()],
        ensure_ascii=False, indent=1), encoding="utf-8")
    exported = {}
    profiles = {p.name.casefold(): p for p in Profile.list_all()} if args.attempts else {}
    if args.attempts:
        (out / "attempts").mkdir(exist_ok=True)
    for name in args.attempts:
        profile = profiles.get(name.casefold())
        if profile is None:
            print(f"No profile called {name} in {PROFILES_DIR}.")
            return 1
        events = [export_attempt(e) for e in attempts.read(profile) if e.get("type") == "attempt"]
        write_jsonl(out / "attempts" / f"{profile.path.stem}.jsonl", events)
        exported[profile.name] = len(events)
    manifest = {"format": "gtutor-olr-export", "format_version": FORMAT_VERSION,
                "status": "throwaway: OLR's content package format is designed, not built",
                "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "app_commit": _commit(),
                "scorer": attempts.GRADER, "language": "de", "instruction_language": "en",
                "counts": {"items": len(items), "books": len(book_rows),
                           "paragraphs": sum(1 for b in book_rows for u in b["units"] if u["kind"] == "paragraph")},
                "attempts": exported,
                "unmapped": {"no_response": UNMAPPED_NO_RESPONSE}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(items)} items, {len(book_rows)} books"
          + (f", answer logs of {', '.join(exported)}" if exported else "") + f" to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
