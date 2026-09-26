"""The exam practice screens (menu 9): pick an exam, do a part, see what was right and why.

The content and the marking are in exams.py. A part is done like in the real exam: all questions first,
then the results, with an explanation for every mistake and (for listening) the transcript.
"""
from __future__ import annotations

import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from datetime import timedelta

from . import attempts, pictures, sfx, srs, ui, writing_check
from .answers import normalize
from .exams import SKILLS, Exam, ExamItem, Part, choices, is_right, item_id, load_exams, passed
from .speaking import hear, hear_lines
from .ui import console, icon

GRADER = "gtutor.exams/1"
PART_AGAIN = {True: 16, False: 3}   # days until a part comes back: passed / not yet
FEEDBACK_WORDS = 15                  # most words an exam part sends back to the daily practice
MOCK_READY, PART_READY = 0.8, 0.6    # readiness for a full mock exam / for single parts
REPLAY = "0"  # the key for "hear it again" (letters are answers: r = richtig, j = ja, a–h = texts)
SELF_CHECK = {"y": "yes", "n": "no"}


def progress(ctx) -> dict:
    """{exam id: {part id: {"score", "max", "best", "last", "tries"}}} in the profile."""
    return ctx.profile.data.setdefault("exams", {})


def part_status(ctx, exam: Exam, part: Part) -> str:
    done = progress(ctx).get(exam.id, {}).get(part.id)
    if not done:
        return "[hint]not done yet[/]"
    if done.get("due") and done["due"] <= ctx.today.isoformat():
        return f"[key]due again[/] · best {done['best']}/{done['max']}"
    mark = f"[good]{icon('ok')}[/]" if passed(done["best"], done["max"]) else f"[almost]{icon('almost')}[/]"
    return f"{mark} best {done['best']}/{done['max']}" + (f" · last {done['score']}/{done['max']}"
                                                            if done["score"] != done["best"] else "")


def skill_summary(ctx, exam: Exam) -> str:
    """"Lesen 17/25 · Hören –/25 · Schreiben 1/2 done" (best scores)."""
    out = []
    for skill, name in SKILLS.items():
        parts = exam.skill_parts(skill)
        if not parts:
            continue
        done = [progress(ctx).get(exam.id, {}).get(p.id) for p in parts]
        if skill == "writing":
            out.append(f"{name} {sum(1 for d in done if d)}/{len(parts)} done")
        elif any(done):
            out.append(f"{name} {sum(d['best'] for d in done if d)}/{sum(p.max_points for p in parts)}")
        else:
            out.append(f"{name} –/{sum(p.max_points for p in parts)}")
    return " · ".join(out)


# ----- menus -----

def menu(ctx) -> None:
    exams, problems = load_exams()
    while True:
        ui.clear()
        ui.title("Exam practice", "in the format of the Goethe-Zertifikat")
        console.print("Practice exams for [bold]A2[/] and [bold]B1[/] (B1 is what most jobs in Germany ask for). "
                      "Reading and listening are marked for you; writing you check against a model answer.\n"
                      "[hint]The texts were written for this app. For the real thing, each exam links the "
                      "official free practice papers.[/]")
        if problems:
            console.print(f"[warn]{ui.plural(len(problems), 'exam problem')}: run tools/validate_content.py.[/]")
        if not exams:
            console.print("[warn]No practice exams yet (content/exams/).[/]")
            ui.keys({"": "back"})
            return
        for n, exam in enumerate(exams, 1):
            console.print(f"  [key]{n}[/]  [bold]{exam.level}[/] · {ui.escape(exam.title)}  "
                          f"[hint]{ui.escape(skill_summary(ctx, exam))}[/]")
        choice = ui.keys({str(n): "" for n in range(1, len(exams) + 1)} | {"": "back"})
        if not choice:
            return
        exam_screen(ctx, exams[int(choice) - 1])


def exam_screen(ctx, exam: Exam) -> None:
    while True:
        ui.clear()
        ui.title(f"{exam.level} · {exam.title}", exam.style)
        if exam.about_en:
            console.print(ui.escape(exam.about_en))
        console.print(f"[bold]{ui.escape(advice(ctx, exam.level))}[/]")
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("")
        table.add_column("Part")
        table.add_column("Time", justify="right")
        table.add_column("Result")
        for n, part in enumerate(exam.parts, 1):
            table.add_row(f"[key]{n}[/]", ui.escape(part.title_de), f"{part.minutes} min" if part.minutes else "",
                          part_status(ctx, exam, part))
        console.print(table)
        console.print(f"[hint]Pass mark: {round(100 * 0.6)}% of the points in each module.[/]")
        if exam.official_practice:
            console.print("[hint]Official free practice papers (do at least one before the real exam):[/]")
            for link in exam.official_practice:
                console.print(f"[hint]  • {ui.escape(link.get('title', ''))}: {ui.escape(link.get('url', ''))}[/]")
        choice = ui.keys({str(n): "" for n in range(1, len(exam.parts) + 1)} | {"": "back"})
        if not choice:
            return
        part = exam.parts[int(choice) - 1]
        do_part(ctx, exam, part)


# ----- reading and listening -----

def _intro(ctx, exam: Exam, part: Part) -> None:
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de}", f"{len(part.items)} questions"
             + (f" · about {part.minutes} min" if part.minutes else ""))
    ui.todo("listen" if part.skill == "listening" else "read", what=part.instructions_en or "Answer every question.")
    if part.skill == "listening":
        if ctx.audio.can_speak:
            console.print(f"You can hear each recording {ui.plural(part.plays, 'time')} "
                          f"(press [key]{REPLAY}[/] to hear it again). Read the questions first!")
        else:
            console.print("[warn]No sound here, so you read the recordings instead (that's easier than the exam).[/]")
    console.print(f"[hint]Answer with the letter. {ui.DONT_KNOW} = don't know. q = stop (nothing is saved).[/]")
    if part.example:
        ui.keys({"": "see the example"})
        _example(ctx, exam, part)
    else:
        ui.keys({"": "start"})


def _example(ctx, exam: Exam, part: Part) -> None:
    """The solved example (Beispiel) before the real questions, like the real exam. Not scored."""
    ex = part.example
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de} · Beispiel", "an example with its answer: not scored")
    text = part.text(ex.text) if ex.text else None
    if part.skill == "listening" and text is not None:
        if ctx.audio.can_speak:
            console.print("[hint]Listen to the example.[/]")
            play_recording(ctx, [text])
        else:
            console.print(ui.german(text.transcript, "Recording (read)"))
    elif text is not None:
        console.print(ui.german(text.transcript, text.title or "Text"))
    pictured = show_pictures(ctx, ex, part)
    console.print(_question_panel(ex, part, 0, pictured))
    label = choices(ex, part).get(ex.answer) if ex.type == "match" else ex.options.get(ex.answer, "")
    console.print(f"[good]{icon('ok')} Lösung: {ui.escape(ex.answer)}[/]" + (f"  [de]{ui.escape(label)}[/]" if label else ""))
    console.print(f"[note]{ui.escape(ex.explain_en)}[/]")
    ui.keys({"": "start the questions"})


def play_recording(ctx, texts: list) -> None:
    """Listening texts one after the other: a conversation with a voice per speaker, an announcement in one."""
    for text in texts:
        if text.lines:
            hear_lines(ctx, text.lines)
        else:
            hear(ctx, text.de, slow=False)


def _blocks(part: Part) -> list[tuple[list[str], list[ExamItem]]]:
    """Listening: questions grouped by the recording they're about ([text ids], [items]). Questions that
    don't name a text are about all the part's recordings."""
    blocks: list[tuple[list[str], list[ExamItem]]] = []
    for item in part.items:
        texts = [item.text] if item.text else [t.id for t in part.texts]
        if blocks and blocks[-1][0] == texts:
            blocks[-1][1].append(item)
        else:
            blocks.append((texts, [item]))
    return blocks


def show_pictures(ctx, item: ExamItem, part: Part) -> bool:
    """The answer choices as pictures, like the real exam (a row of up to 5; more go on further rows).
    False if there are none or they can't be shown here (then the written choices are shown)."""
    if item.type == "mc":
        row = [(key, pictures.IMAGES_DIR / path) for key, path in item.pictures.items()]
    elif item.type == "match":
        row = [(t.id, pictures.IMAGES_DIR / t.picture) for t in part.texts if t.id in choices(item, part) and t.picture]
    else:
        return False
    if not row:
        return False
    settings = {**ctx.settings, **({"pictures": ctx.profile.data["pictures"]} if ctx.profile.data.get("pictures") else {})}
    shown = True
    for start in range(0, len(row), 5):
        shown = pictures.show_row(console, settings, row[start:start + 5]) and shown
    return shown


def _question_panel(item: ExamItem, part: Part, n: int, pictured: bool = False) -> Panel:
    body = Text(f"{n}. {item.question}", style="bold")
    if pictured:
        body.append("\n\n   Look at the pictures: " + "  ".join(choices(item, part)), style="hint")
        if item.type == "match" and part.none_allowed:
            body.append("   (x = none fits)", style="hint")
    elif item.type == "mc":
        for key, label in item.options.items():
            body.append(f"\n   {key}  {label}", style="de")
    elif item.type == "match":
        body.append("\n")
        for key, label in choices(item, part).items():
            body.append(f"\n   {key}  {label}", style="de")
    else:
        body.append("\n\n   " + "   ".join(f"{k} = {v}" for k, v in choices(item, part).items()), style="hint")
    return Panel(body, border_style="blue", padding=(0, 2))


def _ask(ctx, item: ExamItem, part: Part, n: int, header: str, shown: list, replay=None) -> str:
    """One question; returns the key typed ('' = don't know). shown: panels to show above the question."""
    while True:
        ui.clear()
        ui.title(f"{ctx.step}{header}")
        for panel in shown:
            console.print(panel)
        pictured = show_pictures(ctx, item, part)
        console.print(_question_panel(item, part, n, pictured))
        options = {k: "" for k in choices(item, part)} | {ui.DONT_KNOW: "don't know"}
        if replay and replay["left"] > 0:
            options[REPLAY] = f"hear it again ({replay['left']} left)"
        if item.type == "match" and part.skill == "reading":
            options["t"] = "show all the texts"
        choice = ui.keys(options)
        if choice == REPLAY:
            replay["left"] -= 1
            play_recording(ctx, replay["texts"])
        elif choice == "t":
            ui.clear()
            for text in part.texts:
                if text.id in choices(item, part):
                    console.print(ui.german(text.transcript, f"{text.id} · {text.title}" if text.title else text.id))
            ui.keys({"": "back to the question"})
        else:
            return "" if choice == ui.DONT_KNOW else choice


def run_part(ctx, exam: Exam, part: Part) -> None:
    _intro(ctx, exam, part)
    started = time.monotonic()
    answers: dict[str, str] = {}
    header = f"{exam.level} · {part.title_de}"
    if part.skill == "reading":
        for n, item in enumerate(part.items, 1):
            text = part.text(item.text) if item.text else None
            shown = [ui.german(text.transcript, text.title or "Text")] if text else []
            answers[item.id] = _ask(ctx, item, part, n, f"{header} · {n} of {len(part.items)}", shown)
    else:
        n = 0
        for text_ids, items in _blocks(part):
            texts = [part.text(t) for t in text_ids]

            ui.clear()
            ui.title(f"{ctx.step}{header} · questions {n + 1}–{n + len(items)}")
            ui.todo("read", "listen", what="Read the questions, then listen.")
            for k, item in enumerate(items, n + 1):
                console.print(_question_panel(item, part, k))
            ui.keys({"": "listen now" if ctx.audio.can_speak else "read the recording"})
            replay, shown = None, []
            if ctx.audio.can_speak:
                play_recording(ctx, texts)
                replay = {"left": part.plays - 1, "texts": texts}
            else:
                shown = [ui.german(t.transcript, "Recording (read)") for t in texts]
            for item in items:
                n += 1
                answers[item.id] = _ask(ctx, item, part, n, f"{header} · {n} of {len(part.items)}", shown, replay)
    minutes = round((time.monotonic() - started) / 60)
    score = _record(ctx, exam, part, answers)
    _results(ctx, exam, part, answers, score, minutes)


def _record(ctx, exam: Exam, part: Part, answers: dict[str, str]) -> int:
    """Every answer to the answer log, the result to the profile. Returns the score."""
    score = 0
    for item in part.items:
        key = answers.get(item.id, "")
        right = bool(key) and is_right(item, key)
        score += right
        text = part.text(item.text) if item.text else None
        attempts.note(key, task=item.type)
        attempts.record(ctx.profile, ctx.today, item=item_id(exam, part, item),
                        item_version=attempts.version(item.question, item.options, item.answer,
                                                      text.transcript if text else ""),
                        competency=f"exam.{part.skill}", subcompetency=f"{exam.level}/{part.id}",
                        context=f"exam.{exam.id}", grader=GRADER,
                        score=attempts.right_or_wrong(right) if key else attempts.no_response("don't know"))
    _save(ctx, exam, part, score, part.max_points)
    _feedback(ctx, part, [i for i in part.items if not (answers.get(i.id) and is_right(i, answers[i.id]))])
    return score


def feedback_words(ctx, part: Part, missed: list[ExamItem]) -> tuple[list[str], list[str]]:
    """Everyday words in the texts behind the missed questions: (started ones, new ones), most common first."""
    index = {}
    for w in ctx.content.words.values():
        if w.bank == "daily":
            bare = normalize(w.de).split()
            if len(bare) == 2 and bare[0] in ("der", "die", "das") or len(bare) == 1:
                index.setdefault(bare[-1], w)
    found = {}
    for item in missed:
        texts = [part.text(item.text)] if item.text else part.texts
        blob = " ".join([item.question, *item.options.values(), *(t.transcript for t in texts if t)])
        for token in normalize(blob).split():
            if (w := index.get(token)) and len(token) > 3:
                found[w.id] = w
    ranked = sorted(found.values(), key=lambda w: w.rank)[:FEEDBACK_WORDS]
    vocab = ctx.profile.data["vocab"]
    started = [w.id for w in ranked if vocab.get(w.id, {}).get("box", 0) >= 1]
    fresh = [w.id for w in ranked if vocab.get(w.id, {}).get("box", 0) == 0]
    return started, fresh


def _feedback(ctx, part: Part, missed: list[ExamItem]) -> None:
    """Missed questions send their texts' words back: known ones to tomorrow's reviews, new ones to the front
    of the new words (docs/LEARNING_DESIGN.md 4.2)."""
    if not missed:
        return
    started, fresh = feedback_words(ctx, part, missed)
    for wid in started:
        srs.apply_practice(ctx.profile.word_state(wid), "wrong", ctx.today)
    if started:
        attempts.record_nudge(ctx.profile, ctx.today, "vocab", started, f"exam miss: {part.id}")
    queue = ctx.profile.data["reading_words"]
    queue[:0] = [wid for wid in fresh if wid not in queue]
    ctx.profile.data.setdefault("exam_feedback", {})["last"] = len(started) + len(fresh)
    ctx.profile.save()


def readiness(ctx, level: str) -> float:
    from . import graph
    nodes = graph.build(ctx.content, load_exams()[0])
    states = graph.mastery(nodes, ctx.profile.data["vocab"], attempts.tail(ctx.profile, 2_000_000), ctx.today)
    return graph.readiness(nodes, states, level)["total"]


def advice(ctx, level: str) -> str:
    ready = readiness(ctx, level)
    if ready >= MOCK_READY:
        return f"Ready for {level}: {round(100 * ready)}%. Time for a full practice exam: all parts, real timing."
    if ready >= PART_READY:
        return f"Ready for {level}: {round(100 * ready)}%. Do single parts now; a full exam from {round(100 * MOCK_READY)}%."
    return (f"Ready for {level}: {round(100 * ready)}%. Try a part to see what it's like, but daily practice "
            f"helps more until {round(100 * PART_READY)}%.")


def do_part(ctx, exam: Exam, part: Part) -> None:
    {"writing": writing, "speaking": speaking}.get(part.skill, run_part)(ctx, exam, part)


def exam_for_goal(ctx, exams: list[Exam]) -> Exam | None:
    """The practice exam for the kid's goal: A2 for A2, B1 for B1 and C1 (the highest there is so far)."""
    goal = ctx.profile.data.get("target") or ctx.profile.data.get("placement", {}).get("band") or "A2"
    order = ["A1", "A2", "B1", "B2", "C1"]
    fitting = [e for e in exams if order.index(e.level) <= order.index(goal)] if goal in order else exams
    return (fitting or exams or [None])[-1]


def todays_part(ctx, exams: list[Exam]) -> tuple[Exam, Part] | None:
    """The exam part for today's lesson: one that's due again, else one not tried yet (reading and listening
    before writing), else the one with the weakest best score."""
    exam = exam_for_goal(ctx, exams)
    if exam is None:
        return None
    due = [(e, p) for e, p in due_parts(ctx, [exam])]
    if due:
        return due[0]
    done = progress(ctx).get(exam.id, {})
    fresh = [p for p in exam.parts if p.id not in done]
    fresh.sort(key=lambda p: p.skill in ("writing", "speaking"))
    if fresh:
        return exam, fresh[0]
    return exam, min(exam.parts, key=lambda p: done[p.id]["best"] / max(done[p.id]["max"], 1))


def run_daily(ctx) -> str | None:
    """Today's lesson, part 3: one exam part. Returns a line for the finish screen (None: no exams)."""
    picked = todays_part(ctx, load_exams()[0])
    if picked is None:
        return None
    exam, part = picked
    do_part(ctx, exam, part)
    done = progress(ctx).get(exam.id, {}).get(part.id)
    if not done or done.get("last") != ctx.today.isoformat():
        return None  # stopped before the end
    return f"Exam practice: {exam.level} {part.title_de}: {done['score']} of {done['max']}" + (
        " · points covered" if part.skill == "writing" else " · speaking points" if part.skill == "speaking" else "")


def due_parts(ctx, exams: list[Exam]) -> list[tuple[Exam, Part]]:
    """Parts tried before whose come-back day has arrived."""
    out = []
    for exam in exams:
        for part in exam.parts:
            done = progress(ctx).get(exam.id, {}).get(part.id)
            if done and done.get("due") and done["due"] <= ctx.today.isoformat():
                out.append((exam, part))
    return out


def _save(ctx, exam: Exam, part: Part, score: int, total: int) -> None:
    done = progress(ctx).setdefault(exam.id, {}).get(part.id, {})
    again = ctx.today + timedelta(days=PART_AGAIN[passed(score, total)])
    progress(ctx)[exam.id][part.id] = {"score": score, "max": total, "best": max(score, done.get("best", 0)),
                                        "last": ctx.today.isoformat(), "tries": done.get("tries", 0) + 1,
                                        "due": again.isoformat()}
    ctx.profile.count(ctx.today, exam_items=total, exam_right=score)
    ctx.profile.save()


def _shown_answer(item: ExamItem, part: Part, key: str) -> str:
    if not key:
        return "–"
    return choices(item, part).get(key, key) if item.type in ("tf", "yesno") else key


def _results(ctx, exam: Exam, part: Part, answers: dict[str, str], score: int, minutes: int) -> None:
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de} · results")
    total = part.max_points
    verdict = (f"[good]{icon('party')} {score} of {total}: that would pass![/]" if passed(score, total)
               else f"[almost]{score} of {total}. The pass mark is {round(0.6 * total + 0.49)}: keep going![/]")
    console.print(verdict + f"  [hint]{minutes} min" + (f" (exam: {part.minutes} min)" if part.minutes else "") + "[/]")
    sfx.play(ctx.audio, "right" if passed(score, total) else "almost")
    wrong = []
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    back = ctx.profile.data.get("exam_feedback", {}).pop("last", 0)
    if back:
        console.print(f"[hint]{ui.plural(back, 'word')} from the texts you missed come back in your next warm-up.[/]")
    for column in ("", "Your answer", "Right answer"):
        table.add_column(column)
    for n, item in enumerate(part.items, 1):
        key = answers.get(item.id, "")
        right = bool(key) and is_right(item, key)
        mark = f"[good]{icon('ok')}[/]" if right else f"[bad]{icon('bad')}[/]"
        mine = _shown_answer(item, part, key)
        correct = item.answer
        table.add_row(f"{mark} {n}", ui.escape(mine), "" if right else ui.escape(correct))
        if not right:
            wrong.append((n, item))
    console.print(table)
    for n, item in wrong:
        console.print(f"[bad]{n}.[/] {ui.escape(item.question)}\n   [note]{ui.escape(item.explain_en)}[/]")
    options = {"": "done"}
    if part.skill == "listening":
        options["t"] = "read the transcripts"
    while ui.keys(options) == "t":
        ui.clear()
        for text in part.texts:
            console.print(ui.german(text.transcript, text.title or text.id))
        options = {"": "done"}


# ----- speaking -----

def said(transcript: str, group: list[str]) -> bool:
    heard = " " + normalize(transcript) + " "
    return any(" " + normalize(word) in heard for word in group)


def speaking(ctx, exam: Exam, part: Part) -> None:
    """Task cards like the real exam; the computer plays the partner in its own voice. Each answer is recorded,
    the speech check writes down what it heard, and the app checks it said enough and the key things; then the
    model answer. Without a microphone the kid speaks and checks against the model answer."""
    from .exams import SPEAKING_POINTS
    from .speaking import record_for
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de}", f"{len(part.tasks)} tasks" + (f" · about {part.minutes} min" if part.minutes else ""))
    ui.todo("say", what=part.instructions_en or "Answer out loud.")
    checking = getattr(ctx.audio, "can_record", False) and getattr(ctx.audio, "can_check_speech", False)
    console.print("The computer plays your partner or the examiner, in a different voice. After a short countdown and "
                  "a beep, you speak." if checking else
                  "[warn]No microphone or speech check here: say your answers out loud, then compare with the model.[/]")
    ui.keys({"": "start"})
    total = 0
    for n, task in enumerate(part.tasks, 1):
        ui.clear()
        ui.title(f"{ctx.step}{exam.level} · {part.title_de} · task {n} of {len(part.tasks)}")
        card = Text(task.card_title, style="bold")
        for line in task.card:
            card.append("\n" + line, style="de")
        console.print(Panel(card, border_style="magenta", padding=(1, 3), width=min(console.width, 44)))
        console.print(Text(task.prompt_de, style="de"))
        if task.prompt_en:
            console.print(f"[hint]{ui.escape(task.prompt_en)}[/]")
        if task.partner_de:
            console.print(f"[magenta]Your partner:[/] [de]{ui.escape(task.partner_de)}[/]")
            hear(ctx, task.partner_de, slow=False, voice="high")
        transcript = ""
        if checking:
            recording = record_for(ctx, task.seconds)
            if recording is not None:
                with console.status("[hint]Listening to your answer…[/]"):
                    transcript = ctx.audio.heard(*recording)
            console.print(f"[hint]I heard:[/] [de]{ui.escape(transcript) or '(nothing)'}[/]")
        else:
            ui.ask("Say your answer out loud, then press Enter.", wait_for_quiet=False)
        console.print(ui.german(task.model_de, "A good answer"))
        hear(ctx, task.model_de, slow=False)
        if checking:
            enough = len(transcript.split()) >= task.min_words
            met = [said(transcript, g) for g in task.keywords]
            key_ok = not task.keywords or sum(met) * 2 >= len(met)
            points = int(enough) + int(key_ok)
            console.print((f"[good]{icon('ok')}[/]" if enough else f"[almost]{icon('almost')}[/]")
                          + f" {len(transcript.split())} words heard (aim for {task.min_words}+)")
            if task.keywords:
                console.print(" ".join(f"[good]{icon('ok')} {ui.escape(g[0])}[/]" if ok else f"[hint]{icon('almost')} {ui.escape(g[0])}[/]"
                                       for g, ok in zip(task.keywords, met)))
            score = {"kind": "polytomous", "points": points, "max": SPEAKING_POINTS, "label": "speaking check"}
            grader = "gtutor.speaking/1"
        else:
            points = SPEAKING_POINTS if ui.keys({"y": "I said something like that", "n": "not yet"}) == "y" else 0
            score = {"kind": "estimated", "raw": points, "max": SPEAKING_POINTS, "confidence": attempts.SELF_CONFIDENCE,
                     "needs_review": True, "label": "self-check"}
            grader = attempts.SELF
        total += points
        attempts.note(transcript, task="speaking")
        attempts.record(ctx.profile, ctx.today, item=f"{exam.id}.{part.id}.{task.id}",
                        item_version=attempts.version(task.prompt_de, task.partner_de, task.keywords),
                        competency="exam.speaking", subcompetency=f"{exam.level}/{part.id}", context=f"exam.{exam.id}",
                        score=score, grader=grader)
        if ui.timed_keys({"": "next task", "r": "hear the good answer again"}, 5) == "r":
            hear(ctx, task.model_de, slow=False)
    _save(ctx, exam, part, total, part.max_points)
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de} · results")
    console.print(f"[good]{icon('party')} {total} of {part.max_points} speaking points.[/]" if passed(total, part.max_points)
                  else f"[almost]{total} of {part.max_points} speaking points. Say a bit more, and use the words on the card.[/]")
    console.print("[hint]The app checks that you said enough and the key things; a real examiner also listens for "
                  "pronunciation and grammar. Compare with the good answers.[/]")
    ui.keys({"": "done"})


# ----- writing -----

def writing(ctx, exam: Exam, part: Part) -> None:
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de}", f"about {part.minutes} min" if part.minutes else "")
    ui.todo("type", what=f"Write about {part.words[1]} words. Cover every point.")
    points = "\n".join(f"  • {p}" for p in part.points)
    console.print(Panel(Text(f"{part.task_de}\n\n{points}", style="de"), title="Aufgabe", border_style="cyan",
                        padding=(1, 2)))
    console.print(f"[hint]{ui.escape(part.task_en)}[/]")
    console.print(ui.umlaut_tip())
    pastes = ui.paste_count()
    started = time.monotonic()
    text = ui.ask_multiline("Your text:")
    pasted = ui.paste_count() > pastes
    words = len(text.split())
    ui.clear()
    ui.title(f"{ctx.step}{exam.level} · {part.title_de} · check it yourself")
    if pasted:
        console.print(f"[bad]{icon('bad')} Pasted text doesn't count. Write it yourself next time.[/]")
    elif words < part.words[0]:
        console.print(f"[almost]{words} words: the exam asks for at least {part.words[0]}.[/]")
    else:
        console.print(f"[good]{words} words.[/] [hint](target: about {part.words[1]})[/]")
    ui.side_by_side("Your text", text, "A model answer", part.model_de)
    covered, found = 0, []
    if text and not pasted:
        report = writing_check.check(text, part, exam.level, ctx.content)
        found = report.points_found
        table = Table(title="What an examiner looks at (the app's estimate)", title_justify="left", box=None,
                      padding=(0, 2), show_header=False)
        for c in report.checks:
            table.add_row(f"[good]{icon('ok')}[/]" if c.ok else f"[almost]{icon('almost')}[/]", c.label,
                          f"[hint]{ui.escape(c.detail)}[/]")
        console.print(table)
        console.print("Did your text do this? Points the app found are ticked already.")
        for n, point in enumerate(part.points):
            if n < len(found) and found[n]:
                console.print(f"  [good]{icon('ok')}[/] [de]{ui.escape(point)}[/]")
                covered += 1
            else:
                console.print(f"  [de]{ui.escape(point)}[/]")
                covered += ui.keys(SELF_CHECK) == "y"
    attempts.note(text, task="writing", pasted=pasted)
    attempts.record(ctx.profile, ctx.today, item=item_id(exam, part), item_version=attempts.version(
                        part.task_de, part.points), competency="exam.writing",
                    subcompetency=f"{exam.level}/{part.id}", context=f"exam.{exam.id}",
                    score=({"kind": "estimated", "raw": covered, "max": len(part.points),
                            "confidence": attempts.SELF_CONFIDENCE, "needs_review": True, "label": "points covered"}
                           if text and not pasted else attempts.no_response("pasted" if pasted else "skipped")),
                    grader=attempts.SELF if text and not pasted else GRADER,
                    words=words, minutes=round((time.monotonic() - started) / 60),
                    points_found_by_app=sum(found) if found else None)
    _save(ctx, exam, part, covered, len(part.points))
    console.print(f"[good]{covered} of {len(part.points)} points covered.[/]" if text and not pasted else "")
    ui.keys({"": "done"})
