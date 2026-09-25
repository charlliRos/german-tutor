"""The exam practice screens (menu 9): pick an exam, do a part, see what was right and why.

The content and the marking are in exams.py. A part is done like in the real exam: all questions first,
then the results, with an explanation for every mistake and (for listening) the transcript.
"""
from __future__ import annotations

import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import attempts, sfx, ui
from .exams import SKILLS, Exam, ExamItem, Part, choices, is_right, item_id, load_exams, passed
from .speaking import hear
from .ui import console, icon

GRADER = "gtutor.exams/1"
REPLAY = "0"  # the key for "hear it again" (letters are answers: r = richtig, j = ja, a–h = texts)
SELF_CHECK = {"y": "yes", "n": "no"}


def progress(ctx) -> dict:
    """{exam id: {part id: {"score", "max", "best", "last", "tries"}}} in the profile."""
    return ctx.profile.data.setdefault("exams", {})


def part_status(ctx, exam: Exam, part: Part) -> str:
    done = progress(ctx).get(exam.id, {}).get(part.id)
    if not done:
        return "[hint]not done yet[/]"
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
        if part.skill == "writing":
            writing(ctx, exam, part)
        else:
            run_part(ctx, exam, part)


# ----- reading and listening -----

def _intro(ctx, exam: Exam, part: Part) -> None:
    ui.clear()
    ui.title(f"{exam.level} · {part.title_de}", f"{len(part.items)} questions"
             + (f" · about {part.minutes} min" if part.minutes else ""))
    ui.todo("listen" if part.skill == "listening" else "read", what=part.instructions_en or "Answer every question.")
    if part.skill == "listening":
        if ctx.audio.can_speak:
            console.print(f"You can hear each recording {ui.plural(part.plays, 'time')} "
                          f"(press [key]{REPLAY}[/] to hear it again). Read the questions first!")
        else:
            console.print("[warn]No sound here, so you read the recordings instead (that's easier than the exam).[/]")
    console.print(f"[hint]Answer with the letter. {ui.DONT_KNOW} = don't know. q = stop (nothing is saved).[/]")
    ui.keys({"": "start"})


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


def _question_panel(item: ExamItem, part: Part, n: int) -> Panel:
    body = Text(f"{n}. {item.question}", style="bold")
    if item.type == "mc":
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
        ui.title(header)
        for panel in shown:
            console.print(panel)
        console.print(_question_panel(item, part, n))
        options = {k: "" for k in choices(item, part)} | {ui.DONT_KNOW: "don't know"}
        if replay and replay["left"] > 0:
            options[REPLAY] = f"hear it again ({replay['left']} left)"
        if item.type == "match" and part.skill == "reading":
            options["t"] = "show all the texts"
        choice = ui.keys(options)
        if choice == REPLAY:
            replay["left"] -= 1
            hear(ctx, replay["text"], slow=False)
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
            spoken = " … ".join(t.spoken for t in texts)
            ui.clear()
            ui.title(f"{header} · questions {n + 1}–{n + len(items)}")
            ui.todo("read", "listen", what="Read the questions, then listen.")
            for k, item in enumerate(items, n + 1):
                console.print(_question_panel(item, part, k))
            ui.keys({"": "listen now" if ctx.audio.can_speak else "read the recording"})
            replay, shown = None, []
            if ctx.audio.can_speak:
                hear(ctx, spoken, slow=False)
                replay = {"left": part.plays - 1, "text": spoken}
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
    return score


def _save(ctx, exam: Exam, part: Part, score: int, total: int) -> None:
    done = progress(ctx).setdefault(exam.id, {}).get(part.id, {})
    progress(ctx)[exam.id][part.id] = {"score": score, "max": total, "best": max(score, done.get("best", 0)),
                                        "last": ctx.today.isoformat(), "tries": done.get("tries", 0) + 1}
    ctx.profile.count(ctx.today, exam_items=total, exam_right=score)
    ctx.profile.save()


def _shown_answer(item: ExamItem, part: Part, key: str) -> str:
    if not key:
        return "–"
    return choices(item, part).get(key, key) if item.type in ("tf", "yesno") else key


def _results(ctx, exam: Exam, part: Part, answers: dict[str, str], score: int, minutes: int) -> None:
    ui.clear()
    ui.title(f"{exam.level} · {part.title_de} · results")
    total = part.max_points
    verdict = (f"[good]{icon('party')} {score} of {total}: that would pass![/]" if passed(score, total)
               else f"[almost]{score} of {total}. The pass mark is {round(0.6 * total + 0.49)}: keep going![/]")
    console.print(verdict + f"  [hint]{minutes} min" + (f" (exam: {part.minutes} min)" if part.minutes else "") + "[/]")
    sfx.play(ctx.audio, "right" if passed(score, total) else "almost")
    wrong = []
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
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


# ----- writing -----

def writing(ctx, exam: Exam, part: Part) -> None:
    ui.clear()
    ui.title(f"{exam.level} · {part.title_de}", f"about {part.minutes} min" if part.minutes else "")
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
    ui.title(f"{exam.level} · {part.title_de} · check it yourself")
    if pasted:
        console.print(f"[bad]{icon('bad')} Pasted text doesn't count. Write it yourself next time.[/]")
    elif words < part.words[0]:
        console.print(f"[almost]{words} words: the exam asks for at least {part.words[0]}.[/]")
    else:
        console.print(f"[good]{words} words.[/] [hint](target: about {part.words[1]})[/]")
    ui.side_by_side("Your text", text, "A model answer", part.model_de)
    covered = 0
    if text and not pasted:
        console.print("Did your text do this? Be honest: it's for you.")
        for point in part.points:
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
                    words=words, minutes=round((time.monotonic() - started) / 60))
    _save(ctx, exam, part, covered, len(part.points))
    console.print(f"[good]{covered} of {len(part.points)} points covered.[/]" if text and not pasted else "")
    ui.keys({"": "done"})
