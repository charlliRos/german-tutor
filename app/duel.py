"""Duel: two players on the same Wi-Fi get the same words and race. `gtutor host` / `gtutor join <ip>`.

The host decides everything that counts: which words, when the round starts, and the final scores
(it scores both players' answers itself with the same checks). Scores shown during the round are only
a live view. Networking is in lan.py; this file is the game and its screens.

Protocol (one JSON object per line, see lan.py): hello -> welcome | error, challenge -> ready -> start,
progress (after every answer), finished (the guest's answers), result, bye. ping keeps the line alive.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, fields

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import lan, presence, sfx, ui
from .answers import ALMOST, CORRECT, WRONG, check_english, check_german
from .content import READING, Word
from .ui import QuitSession, console, icon

QUESTIONS = 10
COUNTDOWN = 3            # seconds before a round starts
FEEDBACK_SECONDS = 1.2   # how long "✔ +137" stays before the next word
SILENT_LIMIT = 10.0      # seconds without any message: the other computer is gone
COMMON_RANK = 1500       # words to fill up with when the players haven't started enough words in common
FAST, SLOW = 2.0, 15.0   # an answer within FAST seconds gets the full speed bonus, after SLOW none


class OpponentLeft(Exception):
    """The other player quit, the connection dropped, or the other computer went silent."""


# ---------- the game: no screen, no network ----------

def points(outcome: str, seconds: float) -> int:
    """100 for right plus up to 50 for speed; 50 for almost; 0 for wrong."""
    if outcome == CORRECT:
        return 100 + round(50 * max(0.0, 1 - max(0.0, seconds - FAST) / (SLOW - FAST)))
    return 50 if outcome == ALMOST else 0


def word_data(word: Word) -> dict:
    """What the other computer needs to ask and check the word (so both play the same words even if one
    computer has an older word list)."""
    keep = {"id", "bank", "de", "en", "pos", "de_alt", "plural", "example_de", "example_en"}
    return {k: v for k, v in asdict(word).items() if k in keep}


def grade(question: dict, answer: str) -> str:
    if not answer:
        return WRONG
    known = {f.name for f in fields(Word)}
    word = Word(**{k: v for k, v in question["word"].items() if k in known})
    check = check_german(answer, word) if question["direction"] == "en2de" else check_english(answer, word)
    return check.outcome


def score(questions: list[dict], answers: list[dict]) -> int:
    """answers: [{"answer": str, "seconds": float}], one per question (missing ones score 0)."""
    total = 0
    for question, answer in zip(questions, answers):
        try:
            total += points(grade(question, str(answer.get("answer", ""))), float(answer.get("seconds", SLOW)))
        except (AttributeError, TypeError, ValueError):
            continue  # a broken answer from the other computer scores nothing
    return total


def pick_questions(content, started_a: set[str], started_b: set[str], rng, count: int = QUESTIONS) -> list[dict]:
    """Words both players have started first (fair: both have met them), then common everyday words."""
    words = content.words
    usable = lambda w: w.bank != READING and w.pos != "phrase" and len(w.de) <= 30  # noqa: E731
    shared = [words[wid] for wid in sorted(started_a & started_b) if wid in words and usable(words[wid])]
    rng.shuffle(shared)
    chosen = shared[:count]
    if len(chosen) < count:
        common = [w for w in words.values() if w.bank == "daily" and w.rank <= COMMON_RANK and usable(w)
                  and w not in chosen]
        rng.shuffle(common)
        chosen += common[: count - len(chosen)]
    rng.shuffle(chosen)
    return [{"word": word_data(w), "direction": rng.choice(("en2de", "de2en"))} for w in chosen]


def results(names: tuple[str, str], questions: list[dict], answers: tuple[list, list]) -> dict:
    """The host's final word: both scores and the winner (None for a draw)."""
    scores = [score(questions, answers[0]), score(questions, answers[1])]
    winner = None if scores[0] == scores[1] else names[scores.index(max(scores))]
    return {"type": "result", "names": list(names), "scores": scores, "winner": winner}


@dataclass
class Standing:
    done: int = 0
    total: int = QUESTIONS
    score: int = 0

    def message(self) -> dict:
        return {"type": "progress", "done": self.done, "total": self.total, "score": self.score}

    def update(self, message: dict) -> bool:
        """Take in a progress message; True if something changed. Nonsense values are ignored."""
        try:
            new = (int(message["done"]), int(message["total"]), int(message["score"]))
        except (KeyError, TypeError, ValueError):
            return False
        changed = new != (self.done, self.total, self.score)
        self.done, self.total, self.score = new
        return changed


# ---------- screens ----------

def board_lines(me: Standing, them: Standing, their_name: str) -> list[str]:
    """YOU and OPPONENT side by side (4 lines, each fits on one row)."""
    col = max(18, min(36, (console.width - 3) // 2))
    full, empty = ("█", "░") if ui.FANCY else ("#", "-")

    def column(title: str, s: Standing) -> list[str]:
        share = s.done / s.total if s.total else 0
        filled = round((col - 2) * share)
        return [title[:col], f"Score: {s.score}", f"Progress: {round(100 * share)}%",
                "[" + full * filled + empty * (col - 2 - filled) + "]"]

    left, right = column("YOU", me), column(their_name.upper(), them)
    return [a.ljust(col) + "   " + b for a, b in zip(left, right)]


def print_board(me: Standing, them: Standing, their_name: str) -> None:
    for line in board_lines(me, them, their_name):
        console.print(line, markup=False, highlight=False, soft_wrap=True)


def show_results(result: dict, my_name: str) -> None:
    ui.clear()
    ui.title("Duel · results")
    table = Table(show_header=True, header_style="bold")
    table.add_column("")
    table.add_column("Player")
    table.add_column("Score", justify="right")
    for n, (name, points_) in enumerate(zip(result["names"], result["scores"]), 1):
        me = " (you)" if name == my_name else ""
        table.add_row(f"Player {n}", ui.escape(name) + me, str(points_))
    console.print(table)
    winner = result.get("winner")
    if winner is None:
        console.print(f"[good]{icon('party')} It's a draw![/]")
    else:
        console.print(f"[good]{icon('party')} Winner: {ui.escape(winner)}[/]"
                      + ("  [hint](that's you!)[/]" if winner == my_name else ""))


# ---------- a round, the same for host and guest ----------

class Round:
    def __init__(self, ctx, conn: lan.Connection, questions: list[dict], my_name: str, their_name: str):
        self.ctx, self.conn, self.questions = ctx, conn, questions
        self.my_name, self.their_name = my_name, their_name
        self.me = Standing(total=len(questions))
        self.them = Standing(total=len(questions))
        self.answers: list[dict] = []
        self.inbox: list[dict] = []  # messages for the caller (finished, result…)
        self.gone = ""               # why the other player is gone ("" while they're here)

    def poll(self, raise_if_gone: bool = True) -> bool:
        """Take in waiting messages. True if the opponent's standing changed. Raises OpponentLeft when
        the other player is gone (after the messages that came before their goodbye, e.g. the result)."""
        changed = False
        while not self.gone and (message := self.conn.receive(timeout=0)) is not None:
            kind = message["type"]
            if kind == lan.CLOSED:
                self.gone = message.get("reason", "the other player left")
            elif kind == "bye":
                self.gone = f"{self.their_name} ended the duel"
            elif kind == "progress":
                changed |= self.them.update(message)
            elif kind != "ping":
                self.inbox.append(message)
        if not self.gone and time.monotonic() - self.conn.last_heard > SILENT_LIMIT:
            self.gone = "the other computer stopped answering (Wi-Fi?)"
        if self.gone and raise_if_gone:
            raise OpponentLeft(self.gone)
        return changed

    def _idle(self, editor) -> None:
        if self.poll():
            editor.redraw_above(board_lines(self.me, self.them, self.their_name))

    def countdown(self) -> None:
        for n in range(COUNTDOWN, 0, -1):
            ui.clear()
            ui.title(f"Duel · {self.my_name} vs {self.their_name}")
            console.print(Panel(Text(f"{len(self.questions)} words. Right = 100 points, fast = up to 50 more.\n"
                                     f"Starting in {n}…", justify="center"), border_style="magenta", padding=(1, 2)))
            end = time.monotonic() + 1
            while time.monotonic() < end:
                self.poll()
                time.sleep(0.1)

    def ask(self, i: int, question: dict) -> str:
        """Show question i with the live board above the prompt; returns the answer ('' = don't know)."""
        word = question["word"]
        while True:
            ui.clear()
            ui.title(f"Duel · word {i} of {len(self.questions)}", f"vs {self.their_name}")
            if question["direction"] == "en2de":
                ui.todo("type", what="Type the German word." + (" Include der / die / das." if word["pos"] == "noun" else ""))
                console.print(Panel(Text(", ".join(word["en"][:2]), style="bold green"), title="English → German",
                                    border_style="green", padding=(1, 2)))
            else:
                ui.todo("type", what="Type what it means in English.")
                console.print(ui.german(word["de"], "German → English", word=True))
            console.print(ui.umlaut_tip() + "  [hint]? = don't know · q = leave[/]")
            print_board(self.me, self.them, self.their_name)
            answer = ui.ask("German:" if question["direction"] == "en2de" else "English:", typed=True,
                            on_idle=self._idle)
            if answer:
                return "" if answer == ui.DONT_KNOW else answer

    def feedback(self, question: dict, outcome: str, gained: int) -> None:
        word = question["word"]
        right = word["de"] if question["direction"] == "en2de" else ", ".join(word["en"][:2])
        if outcome == CORRECT:
            console.print(f"[good]{icon('ok')} Right! +{gained}[/]")
        elif outcome == ALMOST:
            console.print(f"[almost]{icon('almost')} Almost: {ui.escape(right)}  +{gained}[/]")
        else:
            console.print(f"[bad]{icon('bad')} It's: {ui.escape(right)}[/]")
        sfx.play(self.ctx.audio, {CORRECT: "right", ALMOST: "almost", WRONG: "wrong"}[outcome], wait=False)
        end = time.monotonic() + FEEDBACK_SECONDS
        while time.monotonic() < end:
            self.poll()
            time.sleep(0.05)

    def play(self) -> list[dict]:
        """All the questions. Returns this player's answers with their times."""
        self.countdown()
        for i, question in enumerate(self.questions, 1):
            ui.flush_input()
            started = time.monotonic()
            answer = self.ask(i, question)
            seconds = round(time.monotonic() - started, 2)
            outcome = grade(question, answer)
            gained = points(outcome, seconds)
            self.answers.append({"answer": answer, "seconds": seconds})
            self.me.done, self.me.score = i, self.me.score + gained
            self.conn.send(self.me.message())
            self.feedback(question, outcome, gained)
        return self.answers

    def wait_for(self, kind: str, waiting_text: str) -> dict:
        """Show the live board until a message of this kind arrives."""
        def view():
            return Panel(Text("\n".join(board_lines(self.me, self.them, self.their_name)) + f"\n\n{waiting_text}"),
                         title="Duel", border_style="magenta", padding=(1, 2))
        ui.clear()
        with Live(view(), console=console, refresh_per_second=4, transient=True) as live:
            while True:
                changed = self.poll(raise_if_gone=False)
                if (found := next((m for m in self.inbox if m["type"] == kind), None)) is not None:
                    self.inbox.remove(found)
                    return found
                if self.gone:
                    raise OpponentLeft(self.gone)
                if changed:
                    live.update(view())
                time.sleep(0.1)


# ---------- host and guest ----------

def _started(ctx) -> set[str]:
    return {wid for wid, s in ctx.profile.data["vocab"].items() if s.get("box", 0) >= 1}


def _wait_message(conn: lan.Connection, kind: str, timeout: float, leave_on_key: bool = False) -> dict:
    """The next message of this kind. With leave_on_key, any key leaves the duel (QuitSession)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if leave_on_key and ui.key_pressed():
            ui.flush_input()
            raise QuitSession
        message = conn.receive(timeout=0.2)
        if message is None or message["type"] == "ping":
            continue
        if message["type"] == lan.CLOSED:
            raise OpponentLeft(message.get("reason", "the other player left"))
        if message["type"] == "bye":
            raise OpponentLeft("the other player ended the duel")
        if message["type"] == kind:
            return message
    raise OpponentLeft("the other computer didn't answer in time")


def _wait_for_guest(host: lan.Host, ip: str, invite: dict | None = None) -> lan.Connection | None:
    """invite: {"name", "answer"}: a challenge was sent; answer() is True/False once they answered, else None."""
    ui.clear()
    ui.title("Duel · host")
    if invite:
        text = (f"You challenged [bold]{ui.escape(invite['name'])}[/]. They see it on their next screen "
                "and accept in the menu (8).")
    else:
        text = (f"On the other computer, choose [key]8[/] (duel) and [key]j[/] (join), then type:\n\n"
                f"      [bold]{ip}[/]")
    console.print(Panel(Text.from_markup(
        text + "\n\n[hint]Both computers must be on the same Wi-Fi. If Windows asks whether Python may use "
        "the network, click Allow (private networks).[/]"), title="Waiting for the other player…",
        border_style="magenta", padding=(1, 2)))
    console.print("[hint]Press any key to stop waiting.[/]")
    ui.flush_input()
    until = time.monotonic() + presence.INVITE_SECONDS
    while True:
        conn = host.accept()
        if conn:
            return conn
        if ui.key_pressed():
            ui.flush_input()
            return None
        if invite and invite["answer"]() is False:
            raise OpponentLeft(f"{invite['name']} said no this time")
        if invite and time.monotonic() > until:
            raise OpponentLeft(f"{invite['name']} didn't answer the challenge")


def run_host(ctx, port: int = lan.PORT, invite: dict | None = None) -> None:
    try:
        host = lan.Host(port)
    except lan.LanError as exc:
        console.print(f"[warn]{ui.escape(str(exc))}[/]")
        ui.keys({"": "back"})
        return
    conn = None
    try:
        conn = _wait_for_guest(host, lan.my_ip(), invite)
        if conn is None:
            return
        conn.start_pings()
        hello = _wait_message(conn, "hello", 5)
        if hello.get("version") != lan.PROTOCOL:
            conn.send({"type": "error", "message": "The two computers have different app versions: run gtutor update on both."})
            raise OpponentLeft("the other computer has a different app version (run gtutor update on both)")
        guest = str(hello.get("name") or "Player 2")[:30]
        guest_started = {str(x) for x in hello.get("started", [])} if isinstance(hello.get("started"), list) else set()
        me = ctx.profile.name
        conn.send({"type": "welcome", "name": me, "version": lan.PROTOCOL})
        while True:
            questions = pick_questions(ctx.content, _started(ctx), guest_started, ctx.rng)
            conn.send({"type": "challenge", "questions": questions})
            _wait_message(conn, "ready", 10)
            conn.send({"type": "start"})
            rnd = Round(ctx, conn, questions, me, guest)
            mine = rnd.play()
            theirs = rnd.wait_for("finished", f"You're done! Waiting for {guest} to finish…")
            guest_answers = theirs.get("answers") if isinstance(theirs.get("answers"), list) else []
            result = results((me, guest), questions, (mine, guest_answers))
            conn.send(result)
            show_results(result, me)
            if ui.keys({"": "another round", "q": "stop the duel"}) == "q":
                conn.send({"type": "bye"})
                return
    except OpponentLeft as exc:
        console.print(f"[warn]The duel stopped: {ui.escape(str(exc))}.[/]")
        ui.keys({"": "back"})
    except (QuitSession, KeyboardInterrupt):
        if conn:
            conn.send({"type": "bye"})
    finally:
        if conn:
            conn.close()
        host.close()


def run_join(ctx, ip: str, port: int = lan.PORT) -> None:
    conn = None
    try:
        with console.status(f"Connecting to {ip}…"):
            conn = lan.join(ip.strip(), port)
        conn.start_pings()
        conn.send({"type": "hello", "name": ctx.profile.name, "version": lan.PROTOCOL, "started": sorted(_started(ctx))})
        reply = conn.receive(timeout=5)
        while reply is not None and reply["type"] == "ping":
            reply = conn.receive(timeout=5)
        if reply is None or reply["type"] not in ("welcome", "error"):
            raise OpponentLeft("the other computer didn't answer like this app")
        if reply["type"] == "error":
            raise OpponentLeft(str(reply.get("message", "the host said no")))
        host_name = str(reply.get("name") or "Player 1")[:30]
        ui.clear()
        ui.title("Duel · joined")
        console.print(f"Connected to [bold]{ui.escape(host_name)}[/].")
        while True:
            console.print(f"[hint]Waiting for {ui.escape(host_name)} to start a round… (press any key to leave)[/]")
            challenge = _wait_message(conn, "challenge", 3600, leave_on_key=True)
            questions = challenge.get("questions")
            if not isinstance(questions, list) or not questions:
                raise OpponentLeft("the challenge from the host was broken")
            conn.send({"type": "ready"})
            _wait_message(conn, "start", 30)
            rnd = Round(ctx, conn, questions, ctx.profile.name, host_name)
            conn.send({"type": "finished", "answers": rnd.play()})
            result = rnd.wait_for("result", f"You're done! Waiting for {host_name} to finish…")
            if not isinstance(result.get("scores"), list) or not isinstance(result.get("names"), list):
                raise OpponentLeft("the result from the host was broken")
            show_results(result, ctx.profile.name)
            if rnd.gone:  # the host stopped right after the round
                raise OpponentLeft(rnd.gone)
    except lan.LanError as exc:
        console.print(f"[warn]{ui.escape(str(exc))}[/]")
        ui.keys({"": "back"})
    except OpponentLeft as exc:
        console.print(f"[warn]The duel stopped: {ui.escape(str(exc))}.[/]")
        ui.keys({"": "back"})
    except (QuitSession, KeyboardInterrupt):
        if conn:
            conn.send({"type": "bye"})
    finally:
        if conn:
            conn.close()


def menu(ctx) -> None:
    """From the main menu: accept a challenge, challenge someone online, or host / join by address."""
    others = [p for p in ctx.presence.online() if p["status"] != "in a duel"] if ctx.presence else []
    invites = ctx.presence.pending_invites() if ctx.presence else []
    ui.clear()
    ui.title("Duel: play against someone on the same Wi-Fi")
    console.print("You both get the same words: right and fast wins.")
    options = {}
    if invites:
        invite = invites[-1]
        console.print(f"[bold magenta]{ui.escape(invite['name'])} challenges you![/]")
        options.update({"a": f"accept {invite['name']}'s challenge", "d": "say no"})
    for n, other in enumerate(others[:9], 1):
        options[str(n)] = f"challenge {other['name']} ({other['status']})"
    if ctx.presence and not others:
        console.print("[hint]Nobody else is online on this Wi-Fi right now (they need the app open).[/]")
    options.update({"h": "host by address", "j": "join by address", "": "back"})
    choice = ui.keys(options)
    if choice in ("a", "d"):
        accepted = ctx.presence.answer(invite["id"], choice == "a")
        if choice == "a":
            if accepted:
                run_join(ctx, accepted["ip"], accepted["port"])
            else:
                console.print("[warn]That challenge has run out. Challenge them back![/]")
                ui.keys({"": "back"})
    elif choice.isdigit():
        other = others[int(choice) - 1]
        invite_id = ctx.presence.challenge(other["id"])
        try:
            run_host(ctx, invite={"name": other["name"], "answer": lambda: ctx.presence.challenge_answer(invite_id)})
        finally:
            ctx.presence.cancel_challenge()
    elif choice == "h":
        run_host(ctx)
    elif choice == "j":
        last = ctx.profile.data.get("duel_host", "")
        ip = ui.ask(f"The host's address{f' (Enter = {last})' if last else ''}:") or last
        if ip:
            ctx.profile.data["duel_host"] = ip
            ctx.profile.save()
            run_join(ctx, ip)
