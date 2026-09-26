"""Grammar from real sentences: the example sentences of words the kid has already started.

Three kinds of question, all checked against the sentence itself (so the answer is always right):
- article: "Ich gebe d___ Hund einen Knochen." -> dem  (with a tip after mit/für/in…)
- ending:  "Ich habe einen neu___ Laptop." -> en
- order:   the words shuffled, the first one given -> type the sentence
A few a day in the warm-up; misses come back at the end until they're right.
"""
from __future__ import annotations

from dataclasses import dataclass

from rich.panel import Panel
from rich.text import Text

from . import attempts, sfx, ui
from .answers import CORRECT, WRONG, normalize
from .content import bare_word
from .speaking import hear
from .ui import console, icon
from .verbs import NEXT_SECONDS, WRONG_SECONDS, VerbResult

DEFINITE = {"der", "die", "das", "den", "dem", "des"}
EIN_WORDS = ("ein", "kein", "mein", "dein", "sein")
EIN_ENDINGS = ("", "e", "en", "em", "er", "es")
ADJ_ENDINGS = ("e", "en", "em", "er", "es")
DATIVE = {"mit", "bei", "nach", "von", "zu", "aus", "seit", "gegenüber"}
ACCUSATIVE = {"für", "durch", "gegen", "ohne", "um"}
TWO_WAY = {"in", "an", "auf", "über", "unter", "vor", "hinter", "neben", "zwischen"}
ORDER_WORDS = (4, 9)  # sentence length for putting words in order
_CAPITAL_PRONOUNS = {"sie", "ihnen", "ihr", "ihre", "ihren", "ich"}  # capital, but not a noun (Was meinen Sie?)

ENDING_TIP = ("Tip: after der/die/das the ending is -e or -en. After ein/kein/mein the adjective shows "
              "the gender: -er (der), -e (die), -es (das). In the dative and in the plural it's -en.")
ORDER_TIP = ("Tip: in a statement the verb is the 2nd part; in a yes/no question it comes first; "
             "after weil/dass/wenn it goes to the end.")


@dataclass
class Item:
    kind: str       # article, ending, order
    sentence: str   # the whole sentence
    shown: str      # what the kid sees
    answer: str     # the right answer (a word, an ending, or the sentence)
    tip: str = ""   # shown after a wrong answer
    english: str = ""
    full: str = ""  # ending questions: the whole word (neuen), also accepted
    source: str = ""  # id of the word whose example sentence this came from


def _is_noun(token: str) -> bool:
    core = bare_word(token)
    return bool(core) and core not in _CAPITAL_PRONOUNS and token.strip("„“\"'(«»")[:1].isupper()


def _case_tip(prev: str) -> str:
    p = bare_word(prev)
    if p in DATIVE:
        return f"Tip: {p} is always followed by the dative (dem, der, dem; plural den)."
    if p in ACCUSATIVE:
        return f"Tip: {p} is always followed by the accusative (den, die, das)."
    if p in TWO_WAY:
        return f"Tip: {p} + accusative for movement (wohin?), + dative for a place (wo?)."
    return ""


def article_items(sentence: str) -> list[Item]:
    parts = sentence.split()
    items = []
    for i, part in enumerate(parts[:-1]):
        word = bare_word(part)
        nxt = parts[i + 1]
        adjective_between = bare_word(nxt)[-1:] in ("e", "n", "r", "s") and i + 2 < len(parts) and _is_noun(parts[i + 2])
        noun_follows = _is_noun(nxt) or adjective_between
        if not noun_follows or part != part.strip(",.;:!?"):
            continue
        if word in DEFINITE:
            stem = part[0]
        else:
            base = next((b for b in EIN_WORDS if word.startswith(b) and word[len(b):] in EIN_ENDINGS), None)
            if not base:
                continue
            stem = part[:len(base)]
        shown = " ".join(parts[:i] + [stem + "___"] + parts[i + 1:])
        items.append(Item("article", sentence, shown, part, _case_tip(parts[i - 1]) if i else ""))
    return items


def ending_items(sentence: str, adjectives: set[str]) -> list[Item]:
    parts = sentence.split()
    items = []
    for i, part in enumerate(parts[:-1]):
        word = bare_word(part)
        if part != part.strip(",.;:!?") or not _is_noun(parts[i + 1]) or part[:1].isupper():
            continue
        for adj in adjectives:
            if not word.startswith(adj):
                continue
            ending = word[len(adj):]
            if ending not in (("n", "m", "r", "s") if adj.endswith("e") else ADJ_ENDINGS):  # müde -> müden
                continue
            shown = " ".join(parts[:i] + [part[:len(adj)] + "___"] + parts[i + 1:])
            items.append(Item("ending", sentence, shown, ending, ENDING_TIP, full=word))
            break
    return items


def order_item(sentence: str, rng) -> Item | None:
    if any(c in sentence for c in ",;:–—\"„“»«()") or not sentence.rstrip()[-1:] in ".!?":
        return None
    parts = sentence.rstrip(".!?").split()
    if not ORDER_WORDS[0] <= len(parts) <= ORDER_WORDS[1]:
        return None
    rest = parts[1:]
    for _ in range(10):
        shuffled = rest[:]
        rng.shuffle(shuffled)
        if shuffled != rest:
            break
    else:
        return None
    shown = f"{parts[0]} …   [ {'  /  '.join(shuffled)} ]"
    return Item("order", sentence, shown, sentence, ORDER_TIP)


def pool(ctx) -> list:
    """Words the kid has started that have an example sentence."""
    words, vocab = ctx.content.words, ctx.profile.data["vocab"]
    return [words[wid] for wid, s in vocab.items() if s.get("box", 0) >= 1 and wid in words and words[wid].example_de]


def focus_kinds(ctx) -> list[str]:
    """The kinds of question that practise the grammar points to work on next (skill graph frontier)."""
    from . import attempts, graph
    try:
        nodes = graph.build(ctx.content)
        states = graph.mastery(nodes, ctx.profile.data["vocab"], attempts.tail(ctx.profile, 2_000_000), ctx.today)
        level = ctx.profile.data.get("target") or ctx.profile.data.get("placement", {}).get("band") or "A2"
        frontier = graph.frontier(nodes, states, level)
    except (OSError, ValueError, KeyError):
        return []
    kinds = []
    for nid in frontier[:5]:
        for rule in nodes[nid].scored_from:
            kind = str(rule.get("subcompetency", "")).rstrip("*")
            if kind in ("article", "ending", "order") and kind not in kinds:
                kinds.append(kind)
    return kinds


def make_items(ctx, count: int, focus: list[str] | None = None) -> list[Item]:
    """A mix of the three kinds, each from a different sentence. focus: kinds to ask more of (about 70%:
    the grammar being learned now), the rest keeps the others fresh."""
    words = pool(ctx)
    ctx.rng.shuffle(words)
    adjectives = {normalize(w.de) for w in ctx.content.words.values()
                  if w.pos == "adj" and len(normalize(w.de)) >= 3 and " " not in normalize(w.de)}
    kinds = ["article", "ending", "order"]
    if focus:
        kinds = [k for k in focus for _ in range(max(1, round(7 / len(focus))))] + kinds
    items: list[Item] = []
    used = set()
    for n in range(count * 20):
        if len(items) >= count or not words:
            break
        kind = kinds[len(items) % len(kinds)]
        word = words[n % len(words)]
        if word.example_de in used:
            continue
        if kind == "article":
            found = article_items(word.example_de)
        elif kind == "ending":
            found = ending_items(word.example_de, adjectives)
        else:
            found = [x] if (x := order_item(word.example_de, ctx.rng)) else []
        if found:
            item = ctx.rng.choice(found)
            item.english = word.example_en
            item.source = word.id
            items.append(item)
            used.add(word.example_de)
    return items


def check(item: Item, answer: str) -> tuple[str, str]:
    """(outcome, message)."""
    given = normalize(answer)
    if item.kind == "order":
        want = normalize(item.sentence)
        if given in (want, want.split(" ", 1)[-1]):  # with or without the first word, which was given
            return CORRECT, ""
        if sorted(given.split()) == sorted(want.split()):
            return WRONG, "All the right words, but a different order."
        return WRONG, ""
    if item.kind == "ending":
        return (CORRECT, "") if given in (item.answer, normalize(item.full)) else (WRONG, "")
    return (CORRECT, "") if given == normalize(item.answer) else (WRONG, "")


PROMPTS = {"article": ("Type the whole missing word (der, dem, einen …).", "Missing word:"),
           "ending": ("Type the missing ending: -e, -en, -er, -es or -em.", "Ending:"),
           "order": ("Put the words in order: type the whole sentence.", "Sentence:")}


def question(ctx, item: Item, heading: str, repeat: bool = False) -> str:
    ui.clear()
    ui.title(f"{ctx.step}{heading}", "just for practice, no score" if repeat else "grammar from real sentences")
    what, prompt = PROMPTS[item.kind]
    ui.todo("type", what=what)
    console.print(Panel(Text(item.shown, style="de"), subtitle=item.english or None, border_style="cyan",
                        padding=(1, 2)))
    console.print(ui.umlaut_tip())
    answer = ui.ask_answer(prompt)
    outcome, message = check(item, answer) if answer else (WRONG, "")
    attempts.note(answer, outcome, message, item.kind)
    if outcome == CORRECT:
        console.print(f"[good]{icon('ok')} Correct![/]")
        sfx.play(ctx.audio, "right")
    else:
        console.print((f"[bad]{icon('bad')} Not quite.[/] " if answer else "[hint]Here it is:[/] ") + ui.escape(message))
        sfx.play(ctx.audio, "wrong")
    console.print(Panel(Text(item.sentence, style="de"), title="The sentence",
                        border_style="green" if outcome == CORRECT else "red", padding=(0, 2)))
    if outcome != CORRECT and item.tip:
        console.print(f"[note]{ui.escape(item.tip)}[/]")
    hear(ctx, item.sentence, slow=False)
    if outcome == CORRECT:
        console.print("[hint]Next one in a moment… (Enter = go now)[/]")
        ui.pause(NEXT_SECONDS, skippable=True)
        return outcome
    options = {"": "next"}
    if answer:  # e.g. another correct word order: the kid may claim it (logged next to the check's verdict)
        options[ui.CLAIM_KEY] = ui.CLAIM_LABEL
        ui.claim_line()
    if ui.timed_keys(options, WRONG_SECONDS) == ui.CLAIM_KEY:
        console.print("[good]OK, counted as correct.[/]")
        sfx.play(ctx.audio, "right")
        return CORRECT
    return outcome


def log(ctx, item: Item, context: str, outcome: str) -> str:
    """Keep the answer in the answer log (attempts.py); returns the outcome. Questions are made fresh from
    example sentences, so the id is the word the sentence belongs to plus the kind of question."""
    attempts.record(ctx.profile, ctx.today, item=f"{item.source}|grammar.{item.kind}",
                    item_version=attempts.version(item.shown, item.answer, item.full),
                    competency=attempts.GRAMMAR_KINDS[item.kind], subcompetency=item.kind, context=context,
                    score=attempts.right_or_wrong(outcome == CORRECT), grader=attempts.GRADER)
    return outcome


def run_grammar(ctx, first_today: bool) -> VerbResult:
    """A few grammar questions in the day's first warm-up. Misses go into result.missed."""
    result = VerbResult()
    if not first_today:
        return result
    items = make_items(ctx, int(ctx.settings["grammar_per_day"]), focus_kinds(ctx))
    for i, item in enumerate(items, 1):
        outcome = log(ctx, item, "grammar.daily", question(ctx, item, f"Grammar {i} of {len(items)}"))
        result.total += 1
        result.right += outcome == CORRECT
        if outcome != CORRECT:
            result.missed.append(item)
        ctx.profile.count(ctx.today, grammar=1, grammar_right=int(outcome == CORRECT))
        ctx.profile.save()
    return result


def repeat_grammar(ctx, not_yet: list[Item]) -> None:
    not_yet = list(not_yet)
    round_no = 0
    while not_yet:
        round_no += 1
        ctx.rng.shuffle(not_yet)
        not_yet = [item for i, item in enumerate(not_yet, 1)
                   if log(ctx, item, "grammar.repeat",
                          question(ctx, item, f"Grammar again until it sticks · round {round_no} · {i} of {len(not_yet)}",
                                   repeat=True)) != CORRECT]
