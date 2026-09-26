"""Review the answers the kids said were right: python tools/review_claims.py

  python tools/review_claims.py                 one by one: y = accept (the word bank learns it), n = reject,
                                                s = skip for now, q = stop
  python tools/review_claims.py --export F      write the open claims to F (JSON) for someone else, e.g. Astra,
                                                to decide: fill in "decision": "accept" or "reject"
  python tools/review_claims.py --apply F       apply the decisions in F

Accepted answers are added to the word (German answers to de_alt, English ones to en) or the verb (alt), and
content/item_versions.json is updated. Every decision is remembered in data/claims_reviewed.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import claims  # noqa: E402
from app.content import load_content  # noqa: E402
from app.profile import Profile  # noqa: E402


def describe(claim: claims.Claim, words: dict, verbs: dict) -> str:
    if claim.kind == "word" and claim.item in words:
        w = words[claim.item]
        asked = ", ".join(w.en[:2]) if claim.task == "en2de" else w.de
        right = w.de if claim.task == "en2de" else ", ".join(w.en)
        return f"asked: {asked}   accepted so far: {right}"
    if claim.kind == "verb":
        inf, kind = claim.item.split("|")
        v = verbs.get(inf)
        return f"{inf} ({kind})   expected: {v.past if kind == 'past' else v.perfect}" if v else claim.item
    return f"{claim.item} ({claim.task})"


def decide(claim: claims.Claim, decision: str, reviewed: dict) -> str:
    if decision == "accept":
        if not claim.can_add:
            reviewed[claim.key] = "accepted (not added: grammar or book word)"
            return "accepted, but can't be added automatically (grammar question or book key word)"
        if not claims.accept(claim):
            return "not found in the content: skipped"
    reviewed[claim.key] = {"accept": "accepted", "reject": "rejected"}[decision]
    return reviewed[claim.key]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", metavar="FILE")
    parser.add_argument("--apply", metavar="FILE")
    args = parser.parse_args(argv)
    reviewed = claims.load_reviewed()
    content = load_content()
    open_claims = claims.collect(Profile.list_all(), reviewed)
    by_key = {c.key: c for c in open_claims}
    changed = False
    if args.export:
        rows = [{"key": c.key, "kind": c.kind, "task": c.task, "answer": c.response, "times": c.count,
                 "question": describe(c, content.words, content.verbs), "decision": ""} for c in open_claims]
        Path(args.export).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(rows)} open claims written to {args.export}")
        return 0
    if args.apply:
        for row in json.loads(Path(args.apply).read_text(encoding="utf-8")):
            claim = by_key.get(row.get("key"))
            if claim and row.get("decision") in ("accept", "reject"):
                print(f"  {claim.response!r}: {decide(claim, row['decision'], reviewed)}")
                changed = True
    else:
        if not open_claims:
            print("No answers waiting for review.")
        for n, claim in enumerate(open_claims, 1):
            print(f"\n{n}/{len(open_claims)}  {describe(claim, content.words, content.verbs)}")
            print(f"   the kid's answer: {claim.response!r}   ({claim.count}x, {', '.join(sorted(claim.kids))})")
            answer = input("   right? y = accept, n = reject, s = skip, q = stop: ").strip().lower()
            if answer == "q":
                break
            if answer in ("y", "n"):
                print(f"   {decide(claim, 'accept' if answer == 'y' else 'reject', reviewed)}")
                changed = True
    if changed:
        claims.save_reviewed(reviewed)
        from item_versions import main as update_versions
        update_versions(["--update"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
