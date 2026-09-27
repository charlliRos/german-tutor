"""The scripted lesson replay, headless: gtutor's half of the gtutor / de-tutor benchmark pair.

    python tools/bench_replay.py bench_lesson.json [--audio]

The script is the same file de-tutor's `de-tutor --replay` reads (de-tutor/bench/lesson.json):
{"learner": "bench", "start": "2026-09-28", "days": 10, "seed": 1, "data": "bench/out",
 "pattern": ["right", "right", "almost", "right", "right", "wrong", "right", "right", "claim", "right"]}

It changes nothing in the app. It swaps the screen and keyboard for a scripted learner that answers by the
pattern (right = the expected answer, almost = one letter short, wrong = "xyzzy", claim = wrong, then
"my answer was right too"), presses Enter and never waits. Screens are still drawn (to a null device), and
every file is really written.

To match de-tutor's phase 1 (vocabulary warm-up only), the verbs, der/die/das and grammar sections, the
sentence tasks and the speaking turns are switched off. --audio also loads the voice (Piper and onnxruntime),
as the real app does at start, but nothing is said. Prints the same JSON fields as de-tutor.
"""
from __future__ import annotations

import time

T0 = time.perf_counter()

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("script")
    parser.add_argument("--audio", action="store_true", help="load the voice at start, as the app does")
    args = parser.parse_args()
    cfg = json.loads(Path(args.script).read_text(encoding="utf-8"))
    data = Path(cfg.get("data", "bench/out")).resolve()
    shutil.rmtree(data, ignore_errors=True)
    os.environ["GTUTOR_PROFILES"] = str(data / "profiles")  # read by app.config at import
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(ROOT))

    from app import main as gmain  # everything the app imports at start
    from app import genders, grammar, sfx, ui, verbs, warmup
    from app.config import load_settings
    from app.content import load_content
    from app.profile import Profile

    settings = load_settings()
    settings.update(speak_chance=0, sentence_tasks={"gap": 0, "dictation": 0}, share_on_wifi=False)
    content = load_content()
    if args.audio:
        from app.audio import Audio
        audio = Audio(settings, enabled=True)
    else:
        class NoAudio:
            can_speak = False
            can_check_speech = False
            problems: list[str] = []
        audio = NoAudio()
    ready_ms = (time.perf_counter() - T0) * 1000

    pattern = cfg["pattern"]
    state = {"next": 0, "answers": 0, "claim": False, "expected": ""}

    def ask_answer(prompt: str, on_idle=None) -> str:
        move = pattern[state["next"] % len(pattern)]
        state["next"] += 1
        state["answers"] += 1
        state["claim"] = move == "claim"
        expected = state["expected"]
        return {"right": expected, "almost": expected[:-1]}.get(move, "xyzzy")

    def keys(options: dict, seconds: float = 0) -> str:
        if state["claim"] and ui.CLAIM_KEY in options:
            state["claim"] = False
            return ui.CLAIM_KEY
        return ""

    original_quiz = warmup.quiz

    def quiz(ctx, word, direction, second_chance=False):
        state["expected"] = word.de if direction == "en2de" else word.en[0]
        return original_quiz(ctx, word, direction, second_chance)

    nothing = lambda *a, **k: None  # noqa: E731
    ui.console.file = open(os.devnull, "w", encoding="utf-8")  # screens are drawn, to nowhere
    for module, name, value in [
        (ui, "clear", nothing), (ui, "pause", nothing), (ui, "ask_answer", ask_answer),
        (ui, "ask", lambda *a, **k: ""), (ui, "keys", keys), (ui, "timed_keys", keys),
        (ui, "paste_count", lambda: 0), (sfx, "play", nothing),
        (warmup, "hear", nothing), (warmup, "speak_and_compare", lambda *a, **k: True), (warmup, "quiz", quiz),
        (verbs, "run_verbs", lambda ctx, first: verbs.VerbResult()), (verbs, "repeat_verbs", nothing),
        (genders, "run_genders", lambda ctx, first: verbs.VerbResult()), (genders, "repeat_genders", nothing),
        (grammar, "run_grammar", lambda ctx, first: verbs.VerbResult()), (grammar, "repeat_grammar", nothing),
    ]:
        setattr(module, name, value)

    start = date.fromisoformat(cfg["start"])
    profile = Profile.open_or_create(cfg.get("learner", "bench"))
    per_day = []
    t_replay = time.perf_counter()
    for d in range(int(cfg.get("days", 1))):
        day = start + timedelta(days=d)
        ctx = gmain.Context(settings, content, profile, audio, random.Random(int(cfg.get("seed", 1)) + d), day)
        before = state["answers"]
        result = warmup.run_warmup(ctx)
        per_day.append({"date": day.isoformat(), "answers": state["answers"] - before,
                        "graded": result.graded if result else 0})
    wall_ms = (time.perf_counter() - t_replay) * 1000
    answers = max(state["answers"], 1)
    log_bytes = profile.attempts_path.stat().st_size if profile.attempts_path.exists() else 0
    print(json.dumps({
        "app": "gtutor",
        "label": "native proxy",
        "host": {"os": platform.system().lower(), "arch": platform.machine().lower(), "cpus": os.cpu_count()},
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "audio_loaded": bool(args.audio),
        "ready_ms": round(ready_ms, 1),
        "words_in_bank": len(content.words),
        "days": len(per_day),
        "answers": state["answers"],
        "wall_ms": round(wall_ms, 1),
        "ms_per_answer": round(wall_ms / answers, 3),
        "attempts_log_bytes": log_bytes,
        "profile_bytes": profile.path.stat().st_size,
        "log_bytes_per_1000_answers": log_bytes * 1000 // answers,
        "per_day": per_day,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
