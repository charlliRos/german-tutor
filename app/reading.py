"""Daily reading: the next paragraph of a classic in 3 rounds, then a look back at earlier paragraphs.

Learning is repetition. A new paragraph is translated, read out loud and translated back. After it,
each session looks back at earlier paragraphs: every paragraph comes back in each of the next
REVIEW_SESSIONS sessions (session 3 repeats sessions 1 and 2) AND on REVIEW_DAYS after it was learned.
A look back marked "needs work" (or skipped) doesn't count, so it comes back next session.
"""
from __future__ import annotations

import difflib
from datetime import datetime, timedelta

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import sfx, ui
from .answers import normalize, real_try
from .config import DEFAULTS
from .content import Book, Unit, balance_quotes, sentences
from .speaking import hear, speak_and_compare
from .ui import console, icon

SELF_GRADES = {"1": "needs work", "2": "mostly right", "3": "nailed it"}
NEEDS_WORK = SELF_GRADES["1"]
REVIEW_SESSIONS = 2
REVIEW_DAYS = (1, 3, 7, 16, 35)  # the same ladder as the words
CAUGHT_EXTRA_SESSIONS = 2  # pasted or random answers: the paragraph comes back in this many more sessions


def current_book(ctx) -> Book | None:
    """The chosen book, or the next one that still has unread paragraphs."""
    books = ctx.content.books
    ids = [b.id for b in books]
    start = ids.index(ctx.profile.data["current_book"]) if ctx.profile.data["current_book"] in ids else 0
    for book in books[start:] + books[:start]:
        if book.next_unit(ctx.profile.book_state(book.id)["next"]) is not None:
            return book
    return None


def choose_book(ctx) -> str:
    """Pick the book to read. Returns a short message for the menu ("" if nothing changed)."""
    books = ctx.content.books
    narrow = console.width < 70
    ui.title("Choose a book")
    table = Table(caption=f"{icon('current')} = reading now", caption_justify="left")
    for col in ("#", "Title") + (() if narrow else ("Author", "Level")) + ("Paragraphs read",):
        table.add_column(col)
    for i, b in enumerate(books, 1):
        nxt = ctx.profile.book_state(b.id)["next"]
        read = f"{icon('done')} finished" if b.finished(nxt) else f"{b.parts_read(nxt)} of {b.parts}"
        mark = f" {icon('current')}" if b.id == ctx.profile.data["current_book"] else ""
        table.add_row(str(i), b.short_title + mark, *(() if narrow else (b.author, b.level)), read)
    console.print(table)
    while True:
        answer = ui.ask("Book number (Enter to keep the current one):")
        if not answer:
            return ""
        if not (answer.isdigit() and 1 <= int(answer) <= len(books)):
            console.print(f"[warn]'{ui.escape(answer)}' isn't a book number. Pick 1–{len(books)}, "
                          "or press Enter.[/]")
            continue
        book = books[int(answer) - 1]
        state = ctx.profile.book_state(book.id)
        if book.finished(state["next"]):
            console.print(f"You've already finished {book.short_title}.")
            if ui.keys({"y": "read it again from the start", "": "pick another book"}) != "y":
                continue
            state["next"] = 1
        elif book.parts_read(state["next"]):
            console.print(f"You've read {book.parts_read(state['next'])} of {book.parts} paragraphs "
                          f"of {book.short_title}.")
            if ui.keys({"": "carry on where I stopped", "s": "start again from the beginning"}) == "s":
                state["next"] = 1
        ctx.profile.data["current_book"] = book.id
        ctx.profile.save()
        return f"[good]Now reading: {ui.escape(book.short_title)}[/]"


def _replay_until_enter(ctx, text: str, enter_label: str) -> None:
    options = {"": enter_label}
    if ctx.audio.can_speak:
        options["r"] = "hear the German again"
        options["s"] = "read it out loud myself"
    while (choice := ui.keys(options)) != "":
        if choice == "r":
            hear(ctx, text, slow=False)
        else:
            speak_and_compare(ctx, text, long_text=True)


def _explain(unit: Unit) -> None:
    console.print(ui.english(unit.en, "What it means"))
    if unit.explain_en:
        console.print(Panel(Text(unit.explain_en), title="What's going on", border_style="magenta", padding=(1, 2)))
    if unit.words:
        console.print(ui.key_words(unit.words))


def _self_grade(ctx, german_text: str | None) -> str:
    console.print("How did you do? Compare honestly. This is for you, not a score.")
    options = dict(SELF_GRADES)
    if german_text and ctx.audio.can_speak:
        options["r"] = "hear the German"
    while True:
        choice = ui.keys(options)
        if choice != "r":
            return SELF_GRADES[choice]
        hear(ctx, german_text, slow=False)


def _not_a_try(pastes_before: int, answer: str, reference: str, source: str = "") -> str:
    """Why an answer isn't a real try ('' if it is): something was pasted, or it's random or copied."""
    if ui.paste_count() > pastes_before:
        return "you pasted text in. Type it yourself!"
    return real_try(answer, reference, source) if answer else ""


def _caught(ctx, reason: str) -> None:
    ctx.profile.count(ctx.today, caught=1)  # for the parent's report
    ctx.profile.save()
    sfx.play(ctx.audio, "wrong")
    console.print(f"[bad]{icon('bad')} Not a real try:[/] {ui.escape(reason)}")


def _do_it_again(ctx, what: str) -> None:
    ui.clear()
    ui.title(f"{ctx.step}Once more, properly")
    console.print(Panel(Text.from_markup(
        f"Pasted or random answers count as skipping, so {what} starts again now.\n"
        f"It also comes back [bold]{CAUGHT_EXTRA_SESSIONS} extra times[/] in the next sessions.\n"
        f"[hint]Don't know something? Type {ui.DONT_KNOW}: that's always OK.[/]"),
        border_style="red", padding=(1, 2)))
    ui.keys({"": "start again"})


def _translate(ctx, book: Book, unit: Unit, direction: str, heading: str, review: bool = False) -> dict:
    """One translation. The journal gets it as soon as it's typed, even if they stop at the self-grade.
    entry["caught"] says why, if it wasn't a real try (pasted, random, or the given text copied)."""
    to_english = direction == "de2en"
    reference = unit.en if to_english else unit.de
    entry = {"date": datetime.now().isoformat(timespec="minutes"), "book": book.id, "unit": unit.part,
             "task": direction, **({"review": True} if review else {})}
    ui.clear()
    ui.title(f"{ctx.step}{heading}: translate into {'English' if to_english else 'German'}", book.short_title)
    if to_english:
        console.print(ui.german(unit.de, "German"))
    else:
        console.print(ui.english(unit.en, "English"))
        if unit.words:
            console.print(ui.key_words(unit.words))
        console.print(ui.umlaut_tip())
    pastes = ui.paste_count()
    answer = ui.ask_multiline(f"Your {'English' if to_english else 'German'} translation:")
    caught = _not_a_try(pastes, answer, reference, unit.de if to_english else unit.en)
    if not answer or caught:  # typed ? (or not a real try): show the answer, the round counts as skipped
        entry.update(answer=answer, skipped=True, **({"caught": caught} if caught else {}))
        ctx.profile.add_journal(entry)
        if caught:
            _caught(ctx, caught)
        console.print(Panel(Text(reference, style="en" if to_english else "de"),
                            title="Reference translation" if to_english else "Original German",
                            border_style="green" if to_english else "cyan", padding=(1, 2)))
        if not to_english:
            hear(ctx, unit.de, slow=False)
        ui.keys({"": "continue"})
        return entry
    entry.update(answer=answer, self_grade="not graded")
    try:
        ui.side_by_side("Your translation", answer,
                        "Reference translation" if to_english else "Original German", reference)
        if not to_english:
            hear(ctx, unit.de, slow=False)
        entry["self_grade"] = _self_grade(ctx, None if to_english else unit.de)
    finally:
        ctx.profile.add_journal(entry)
    return entry


def _sentence_look_back(ctx, book: Book, unit: Unit, direction: str, heading: str) -> tuple[bool, str] | None:
    """Translate a few sentences of the paragraph in a row, one at a time: quicker than the whole
    paragraph, so more repetitions fit in. Returns (none needed work, why it wasn't a real try or '');
    None if the paragraph has no sentence-by-sentence translation (then the whole paragraph is used)."""
    pairs = [(balance_quotes(de, "de"), balance_quotes(en, "en")) for de, en in unit.sentence_pairs
             if len(de.split()) >= 3]
    if not pairs:
        return None
    count = max(1, int(ctx.settings["look_back_sentences"]))
    if len(pairs) > count:
        start = ctx.rng.randrange(len(pairs) - count + 1)
        pairs = pairs[start:start + count]
    to_english = direction == "de2en"
    ok = True
    for i, (de, en) in enumerate(pairs, 1):
        source, reference = (de, en) if to_english else (en, de)
        entry = {"date": datetime.now().isoformat(timespec="minutes"), "book": book.id, "unit": unit.part,
                 "task": direction, "review": True, "source": source, "reference": reference}
        ui.clear()
        ui.title(f"{ctx.step}{heading}: sentence {i} of {len(pairs)} into {'English' if to_english else 'German'}",
                 book.short_title)
        if to_english:
            console.print(ui.german(de, "German"))
            hear(ctx, de, slow=False)
        else:
            console.print(ui.english(en, "English"))
            if unit.words:
                console.print(ui.key_words(unit.words))
            console.print(ui.umlaut_tip())
        pastes = ui.paste_count()
        answer = ui.ask_answer("Your translation:")
        caught = _not_a_try(pastes, answer, reference, source)
        if not answer or caught:  # typed ? (or not a real try)
            entry.update(answer=answer, skipped=True, **({"caught": caught} if caught else {}))
            ctx.profile.add_journal(entry)
            if caught:
                _caught(ctx, caught)
            console.print(Panel(Text(reference, style="en" if to_english else "de"), title="Here it is",
                                border_style="green" if to_english else "cyan", padding=(1, 2)))
            if not to_english:
                hear(ctx, de, slow=False)
            ui.keys({"": "next"})
            if caught:
                return False, caught
            ok = False
            continue
        entry.update(answer=answer, self_grade="not graded")
        try:
            ui.side_by_side("Your translation", answer,
                            "Reference translation" if to_english else "Original German", reference)
            if not to_english:
                hear(ctx, de, slow=False)
            entry["self_grade"] = _self_grade(ctx, None if to_english else de)
        finally:
            ctx.profile.add_journal(entry)
        ok = ok and entry["self_grade"] != NEEDS_WORK
    return ok, ""


SHADOW_TIMED_UP_TO = 70  # characters: shorter sentences record for a fixed time, longer ones until Enter


def _shadow(ctx, book: Book, unit: Unit, heading: str) -> None:
    """Shadowing: hear a sentence, say it straight after, hear yourself next to the voice. A few
    sentences in a row, so the paragraph's sound and rhythm get repeated too."""
    pairs = unit.sentence_pairs or [(s, "") for s in sentences(unit.de)]
    pairs = [(balance_quotes(de, "de"), balance_quotes(en, "en")) for de, en in pairs if len(de.split()) >= 3]
    pairs = pairs or [(unit.de, "")]
    count = max(1, int(ctx.settings["shadow_sentences"]))
    if len(pairs) > count:
        start = ctx.rng.randrange(len(pairs) - count + 1)
        pairs = pairs[start:start + count]
    for i, (de, en) in enumerate(pairs, 1):
        ui.clear()
        ui.title(f"{ctx.step}{heading}: say it after me · sentence {i} of {len(pairs)}", book.short_title)
        console.print(ui.german(de, "Listen, then say it", subtitle=en or None))
        console.print("[hint]Copy the voice: same speed, same melody. Then you hear yourself next to it.[/]")
        hear(ctx, de, slow=False)
        speak_and_compare(ctx, de, long_text=len(de) > SHADOW_TIMED_UP_TO, slow=False)
        ctx.profile.count(ctx.today, shadowed=1)


def _read_aloud(ctx, book: Book, unit: Unit, heading: str) -> None:
    ui.clear()
    ui.title(f"{ctx.step}{heading}: read it out loud", book.short_title)
    console.print(ui.german(unit.de))
    if ctx.audio.can_speak:
        speak_and_compare(ctx, unit.de, long_text=True)
    else:
        console.print("Read it out loud to yourself, slowly and clearly.")
        ui.keys({"": "done"})


DICTATION_PASS = 0.8  # share of words right for a listen-and-type look back to count


def mark_words(answer: str, sentence: str) -> tuple[Text, float]:
    """The sentence with each word green (typed right), orange (small slip) or red (missing / wrong),
    and the share of words right (a slip counts half)."""
    ref = sentence.split()
    ref_norm = [normalize(w) for w in ref]
    given = [t for w in answer.split() for t in normalize(w).split()]  # word by word, like the sentence
    status = ["bad"] * len(ref)
    matcher = difflib.SequenceMatcher(a=ref_norm, b=given, autojunk=False)
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            status[a1:a2] = ["good"] * (a2 - a1)
        elif op == "replace":
            for i, j in zip(range(a1, a2), range(b1, b2)):
                if difflib.SequenceMatcher(a=ref_norm[i], b=given[j]).ratio() >= 0.75:
                    status[i] = "almost"
    text = Text()
    counted = right = 0
    for word, norm, st in zip(ref, ref_norm, status):
        if not norm:  # a dash or quote on its own
            text.append(word + " ")
            continue
        counted += 1
        right += {"good": 1.0, "almost": 0.5, "bad": 0.0}[st]
        text.append(word, style={"good": "good", "almost": "almost", "bad": "bad"}[st])
        text.append(" ")
    return text, (right / counted if counted else 1.0)


def _dictation(ctx, book: Book, unit: Unit, heading: str) -> tuple[bool, str]:
    """Hear one sentence of the paragraph and type it. Returns (most words were right,
    why it wasn't a real try or '')."""
    choices = [s for s in sentences(unit.de) if 4 <= len(s.split()) <= 20] or sentences(unit.de) or [unit.de]
    sentence = balance_quotes(ctx.rng.choice(choices), "de")
    ui.clear()
    ui.title(f"{ctx.step}{heading}: listen and type", book.short_title)
    console.print("Listen to a sentence from this paragraph and type exactly what you hear.")
    console.print(ui.umlaut_tip())
    hear(ctx, sentence)
    pastes = ui.paste_count()
    while (answer := ui.ask_answer("Type it (r = hear again, ? = show me):")).lower() == "r":
        hear(ctx, sentence)
    caught = _not_a_try(pastes, answer, sentence)
    if caught:
        _caught(ctx, caught)
        console.print(ui.german(sentence, "The sentence"))
        score, ok = 0.0, False
    elif not answer:
        console.print(ui.german(sentence, "The sentence"))
        score, ok = 0.0, False
    else:
        marked, score = mark_words(answer, sentence)
        ok = score >= DICTATION_PASS
        sfx.play(ctx.audio, "right" if score == 1 else "almost" if ok else "wrong")
        console.print(Panel(Text(answer, style="magenta"), title="You typed", border_style="magenta"))
        console.print(Panel(marked, title=f"The sentence · {round(score * 100)}% right",
                            border_style="green" if ok else "red", padding=(1, 2)))
        if not ok:
            console.print("[hint]It comes back next session.[/]")
    ctx.profile.count(ctx.today, dictations=1, dictation_pct=round(score * 100))
    hear(ctx, sentence, slow=False)
    while ui.keys({"": "next", "r": "hear it again"}) == "r":
        hear(ctx, sentence, slow=False)
    return ok, caught


def _story_so_far(ctx, book: Book, state: dict) -> Unit | None:
    """Show English summaries of skipped parts; return the next German unit (None if the book ended)."""
    while True:
        unit = book.next_unit(state["next"])
        if unit is None or unit.kind == "text":
            return unit
        ui.clear()
        ui.title(f"{ctx.step}{book.short_title}", "the story continues")
        console.print(Panel(Text(unit.en), title="Meanwhile in the story…", subtitle=unit.covers or None,
                            border_style="magenta", padding=(1, 2)))
        state["next"] = unit.n + 1
        ctx.profile.save()
        ui.keys({"": "continue"})


def _celebrate(ctx, book: Book) -> None:
    ui.clear()
    text = Text(justify="center")
    text.append(f"{icon('party')}  You finished {book.title}!  {icon('party')}\n\n", style="good")
    text.append(f"{book.author} · {ui.plural(book.parts, 'paragraph')} read in German\n", style="en")
    text.append("Du hast das ganze Buch gelesen. Toll gemacht!", style="de")
    console.print(Panel(text, border_style="green", padding=(1, 4)))
    ui.keys({"": "choose my next book"})
    ui.clear()
    console.print(choose_book(ctx))


def _three_rounds(ctx, book: Book, unit: Unit, header: str) -> tuple[dict, dict]:
    """Listen, then translate it, read it out loud, translate it back. Returns both translations."""
    ui.clear()
    ui.title(header, book.author)
    console.print(ui.german(unit.de))
    console.print("[hint]New paragraph: listen and read along. Then 3 rounds: translate it, "
                  "read it out loud, translate it back.[/]")
    hear(ctx, unit.de, slow=False)
    _replay_until_enter(ctx, unit.de, "round 1: translate it")

    # Round 1: try to understand it before seeing the meaning.
    first = _translate(ctx, book, unit, "de2en", "Round 1 of 3")
    ui.clear()
    ui.title(header, "what it means")
    console.print(ui.german(unit.de))
    _explain(unit)
    _replay_until_enter(ctx, unit.de, "round 2: read it out loud")
    # Round 2: say it.
    _read_aloud(ctx, book, unit, "Round 2 of 3")
    # Round 3: build it again from the English.
    return first, _translate(ctx, book, unit, "en2de", "Round 3 of 3")


def lesson(ctx, book: Book, learned_now: set[str] | None = None) -> bool:
    """One new paragraph in 3 rounds: translate it, read it out loud, translate it back.
    Returns True if it counts as read. Stopping halfway keeps the typed translations (journal),
    and the paragraph starts again next time."""
    state = ctx.profile.book_state(book.id)
    if state["next"] == 1 and book.intro_en:
        ui.clear()
        ui.title(f"{ctx.step}{book.short_title}", book.author)
        console.print(Panel(Text(book.intro_en), title="About this book", border_style="magenta", padding=(1, 2)))
        ui.keys({"": "start reading"})
    unit = _story_so_far(ctx, book, state)
    if unit is None:
        _celebrate(ctx, book)
        return False

    header = f"{ctx.step}Paragraph {unit.part} of {book.total_parts} · {book.short_title}"
    while True:
        first, last = _three_rounds(ctx, book, unit, header)
        if not (first.get("caught") or last.get("caught")):
            break
        # Pasted or random: the paragraph isn't read. It starts again now (or next time, if they stop),
        # and comes back more often afterwards.
        state["caught"] = True
        ctx.profile.save()
        _do_it_again(ctx, "this paragraph")

    counted = not (first.get("skipped") and last.get("skipped"))
    state["next"] = unit.n + 1
    ctx.profile.data["current_book"] = book.id
    if counted:
        ctx.profile.count(ctx.today, units=1)
    _schedule_reviews(ctx, book, unit, CAUGHT_EXTRA_SESSIONS if state.pop("caught", False) else 0)
    if learned_now is not None:
        learned_now.add(f"{book.id}:{unit.n}")
    ctx.profile.save()
    if book.finished(state["next"]):
        _story_so_far(ctx, book, state)  # a closing summary, if the book ends with one
        _celebrate(ctx, book)
    return counted


def _schedule_reviews(ctx, book: Book, unit: Unit, extra_sessions: int = 0) -> None:
    """The paragraph comes back in the next sessions, and its key words join the warm-up."""
    ctx.profile.data["paragraph_reviews"][f"{book.id}:{unit.n}"] = {
        "book": book.id, "n": unit.n, "learned": ctx.today.isoformat(),
        "sessions_left": REVIEW_SESSIONS + extra_sessions,
        "due_days": [(ctx.today + timedelta(days=d)).isoformat() for d in REVIEW_DAYS], "last_task": "en2de"}
    queue = ctx.profile.data["reading_words"]
    queue.extend(wid for wid in unit.word_ids if wid not in queue)


def due_reviews(ctx, skip: set[str] = frozenset(), new_paragraphs: int = 1) -> list[tuple[Book, Unit, dict]]:
    """Paragraphs to look back at: first those from the last sessions (the early repeats matter most),
    then those whose review day has come, most overdue first. `skip` = learned in this session.
    Room for paragraph_reviews_per_session per new paragraph read, so reading 2 a day doesn't crowd them out."""
    books = {b.id: b for b in ctx.content.books}
    today = ctx.today.isoformat()
    out = []
    for key, item in list(ctx.profile.data["paragraph_reviews"].items()):
        book = books.get(item["book"])
        if book is None or key in skip:  # a book that didn't load (e.g. a typo in its file) keeps its reviews
            continue
        unit = next((u for u in book.units if u.n == item["n"] and u.kind == "text"), None)
        if unit is None:  # the paragraph was removed from the book
            del ctx.profile.data["paragraph_reviews"][key]
            continue
        if item["sessions_left"] > 0 or (item["due_days"] and item["due_days"][0] <= today):
            out.append((book, unit, item))
    out.sort(key=lambda r: (r[2]["sessions_left"] == 0,
                            r[2]["learned"] if r[2]["sessions_left"] else r[2]["due_days"][0], r[2]["learned"]))
    return out[: max(0, int(ctx.settings["paragraph_reviews_per_session"])) * max(1, new_paragraphs)]


def _review_task(ctx, last: str) -> str:
    """A different exercise from last time, so each look back practises something else.
    Listen-and-type and shadowing need the voice; an older config.json without them still gets them."""
    weights = {**DEFAULTS["reading_tasks"], **ctx.settings["reading_tasks"]}
    if not ctx.audio.can_speak:
        weights.pop("dictation", None)
        weights.pop("shadow", None)
    tasks = [t for t, w in weights.items() if w > 0]
    tasks = [t for t in tasks if t != last] or tasks or ["de2en"]
    return ctx.rng.choice(tasks)


def _look_back_task(ctx, book: Book, unit: Unit, task: str, heading: str) -> tuple[bool, str]:
    """One look back exercise. Returns (it counts, why it wasn't a real try or '')."""
    if task == "read_aloud":
        _read_aloud(ctx, book, unit, heading)
        return True, ""
    if task == "dictation":
        return _dictation(ctx, book, unit, heading)
    if task == "shadow":
        _shadow(ctx, book, unit, heading)
        return True, ""
    result = _sentence_look_back(ctx, book, unit, task, heading)
    if result is not None:
        return result
    entry = _translate(ctx, book, unit, task, heading, review=True)
    return not entry.get("skipped") and entry.get("self_grade") != NEEDS_WORK, entry.get("caught", "")


def review(ctx, book: Book, unit: Unit, item: dict, i: int, total: int) -> None:
    task = _review_task(ctx, item.get("last_task", ""))
    heading = f"Look back {i} of {total} · paragraph {unit.part}"
    while True:
        ok, caught = _look_back_task(ctx, book, unit, task, heading)
        if not caught:
            break
        # Pasted or random: this look back again now, and the paragraph comes back more often.
        item["sessions_left"] += CAUGHT_EXTRA_SESSIONS
        item["caught"] = item.get("caught", 0) + 1
        ctx.profile.save()
        _do_it_again(ctx, "this look back")
    item["last_task"] = task
    item["last_ok"] = ok
    learned = False
    if ok:  # one good look back counts for this session and every review day that has come
        item["sessions_left"] = max(0, item["sessions_left"] - 1)
        item["due_days"] = [d for d in item["due_days"] if d > ctx.today.isoformat()]
        if not item["sessions_left"] and not item["due_days"]:
            del ctx.profile.data["paragraph_reviews"][f"{book.id}:{unit.n}"]
            learned = True
    else:
        item["misses"] = item.get("misses", 0) + 1
    ctx.profile.count(ctx.today, reviews=1, reviews_missed=int(not ok), paragraphs_learned=int(learned))
    ctx.profile.save()


def look_back(ctx, reviews: list[tuple[Book, Unit, dict]]) -> None:
    if not reviews:
        return
    ui.clear()
    ui.title(f"{ctx.step}Look back")
    console.print(f"Now {ui.plural(len(reviews), 'paragraph')} you read before. Repetition is how it sticks!")
    ui.keys({"": "start"})
    for i, (book, unit, item) in enumerate(reviews, 1):
        review(ctx, book, unit, item, i, len(reviews))


def run_reading(ctx) -> int:
    """New paragraphs until the daily amount is reached (and more if wanted), then a look back at the
    paragraphs of earlier sessions. Returns new paragraphs read."""
    learned_now: set[str] = set()  # paragraphs learned in this session wait for the next ones
    done = lessons = 0
    while True:
        book = current_book(ctx)
        if book is None:
            console.print("[good]You've read every paragraph we have! Ask for new texts.[/]")
            break
        done += lesson(ctx, book, learned_now)
        lessons += 1
        if lessons >= ctx.settings["units_per_day"]:
            reviews = due_reviews(ctx, learned_now)
            ui.clear()
            ui.title(f"{ctx.step}Reading")
            console.print(f"{ui.plural(done, 'paragraph')} read."
                          + (" Then a look back at earlier ones." if reviews else "") + " Want another new one first?")
            if ui.keys({"": "go on" if reviews else "finish reading", "y": "one more paragraph"}) != "y":
                break
    look_back(ctx, due_reviews(ctx, learned_now, len(learned_now)))
    return done
