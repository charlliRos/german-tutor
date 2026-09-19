"""Loads the vocabulary bank and books from content/ (see CONTENT_FORMAT.md)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path

from .answers import english_forms, normalize
from .config import BOOKS_DIR, VERBS_DIR, VOCAB_DIR


@dataclass
class Word:
    id: str
    bank: str
    de: str
    en: list[str]
    pos: str
    topic: str = ""
    level: str = ""
    rank: int = 9999
    de_alt: list[str] = field(default_factory=list)
    plural: str = ""
    note: str = ""
    example_de: str = ""
    example_en: str = ""
    story_de: str = ""     # a sentence from a book paragraph that uses the word
    story_from: str = ""   # that book's short title


@dataclass
class Unit:
    n: int                 # position in the book (1-based), used for progress
    de: str
    en: str
    explain_en: str = ""
    words: list[dict] = field(default_factory=list)
    kind: str = "text"     # "text" = German lesson, "summary" = English bridge over skipped parts
    part: int = 0          # lesson number counting only text units
    covers: str = ""
    word_ids: list[str] = field(default_factory=list)  # its key words in the word practice (see reading_words)
    sentence_pairs: list[tuple[str, str]] = field(default_factory=list)  # (German, English) sentence by sentence


@dataclass
class Book:
    id: str
    title: str
    author: str
    year: int | str
    level: str
    intro_en: str
    units: list[Unit]
    total_parts: int = 0   # German units in the file, including ones not translated yet
    short_title: str = ""  # for headers; long titles are cut down automatically

    @property
    def parts(self) -> int:
        return sum(1 for u in self.units if u.kind == "text")

    def parts_read(self, next_n: int) -> int:
        return sum(1 for u in self.units if u.kind == "text" and u.n < next_n)

    def finished(self, next_n: int) -> bool:
        return not any(u.kind == "text" for u in self.units if u.n >= next_n)

    def next_unit(self, next_n: int) -> Unit | None:
        """The first loaded unit at or after position next_n (untranslated units are skipped)."""
        return next((u for u in self.units if u.n >= next_n), None)


@dataclass
class Verb:
    """An irregular verb: `past` is the er/sie/es form, `perfect` is e.g. "ist gegangen"."""
    inf: str
    en: str
    past: str
    perfect: str
    alt: list[str] = field(default_factory=list)  # other standard forms: "sendete", "hat gesendet"

    @property
    def helper(self) -> str:
        return self.perfect.split()[0]

    @property
    def participle(self) -> str:
        return self.perfect.split()[-1]

    @property
    def past_forms(self) -> list[str]:
        """er ging, du gingst, wir gingen, ihr gingt (er hielt, du hieltest, ihr hieltet)."""
        return person_forms(self.past)


def person_forms(past: str) -> list[str]:
    if past.endswith("e"):
        return [past, past + "st", past + "n", past + "t"]
    return [past, past + ("est" if past[-1] in "sßztd" else "st"), past + "en", past + ("et" if past[-1] in "td" else "t")]


@dataclass
class VerbHit:
    """A sentence in a book that uses a verb form: `kind` is "past" or "perfect"."""
    book_id: str
    unit_n: int
    sentence: str
    form: str
    kind: str


@dataclass
class Content:
    words: dict[str, Word] = field(default_factory=dict)
    books: list[Book] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    verbs: dict[str, Verb] = field(default_factory=dict)
    verb_hits: dict[str, list[VerbHit]] = field(default_factory=dict)  # by infinitive, in book order


def _as_list(value) -> list[str]:
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]


def _shorten(title: str, limit: int = 32) -> str:
    title = title.split(" (")[0].split(". ")[0]
    return title if len(title) <= limit else title[: limit - 1] + "…"


def _load_json(path: Path, problems: list[str]):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.name}: cannot read ({exc})")
        return None


BANKS = {"daily": "everyday", "stem": "STEM", "admin": "official German"}
READING = "reading"  # key words from the books: they join the warm-up once their paragraph is read
BANK_LABELS = {**BANKS, READING: "from your reading"}


def vocab_files(vocab_dir: Path = VOCAB_DIR) -> list[Path]:
    """Everyday lists first, then STEM, then official German, so a shared word stays in the most basic list."""
    order = list(BANKS)
    return sorted(vocab_dir.glob("*.json"),
                  key=lambda p: (order.index(p.stem.split("_")[0]) if p.stem.split("_")[0] in order else 9, p.name))


def meaning_key(de: str, en: list[str]) -> tuple[str, set[str]]:
    return normalize(de), set().union(*(english_forms(e) for e in en))


def is_duplicate(seen: dict[str, list[set[str]]], de: str, en: list[str]) -> bool:
    """Same German AND an overlapping English meaning. 'gerade' = straight vs. even (number) are both kept."""
    key, meanings = meaning_key(de, en)
    if any(meanings & other for other in seen.get(key, [])):
        return True
    seen.setdefault(key, []).append(meanings)
    return False


def load_content(vocab_dir: Path = VOCAB_DIR, books_dir: Path = BOOKS_DIR, verbs_dir: Path = VERBS_DIR) -> Content:
    content = Content()
    seen_meanings: dict[str, list[set[str]]] = {}
    for path in vocab_files(vocab_dir):
        data = _load_json(path, content.problems)
        if not data:
            continue
        bank = data.get("bank", "daily")
        for raw in data.get("words", []):
            try:
                word = Word(
                    id=str(raw["id"]), bank=bank, de=raw["de"].strip(), en=_as_list(raw["en"]),
                    pos=raw.get("pos", "other"), topic=raw.get("topic", ""), level=raw.get("level", ""),
                    rank=int(raw.get("rank", 9999)), de_alt=_as_list(raw.get("de_alt")),
                    plural=raw.get("plural", ""), note=raw.get("note", ""),
                    example_de=raw.get("example_de", ""), example_en=raw.get("example_en", ""),
                )
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                content.problems.append(f"{path.name}: bad word entry {raw!r:.60} ({exc})")
                continue
            if not word.en:
                content.problems.append(f"{path.name}: {word.id} has no English")
                continue
            if word.id in content.words:
                content.problems.append(f"{path.name}: duplicate id {word.id}")
                continue
            if is_duplicate(seen_meanings, word.de, word.en):
                continue  # already in the bank with the same meaning
            content.words[word.id] = word

    for path in sorted(books_dir.glob("*.json")):
        data = _load_json(path, content.problems)
        if not data:
            continue
        units: list[Unit] = []
        part = 0
        # n and part are positions in the file (counting untranslated units too), so saved progress
        # stays valid when a skipped unit gets translated later.
        for n, raw in enumerate(data.get("units", []), 1):
            if raw.get("type") == "summary":
                if raw.get("en"):
                    units.append(Unit(n=n, de="", en=raw["en"].strip(), kind="summary",
                                      covers=raw.get("covers", "")))
                continue
            part += 1
            if not raw.get("de") or not raw.get("en"):
                continue  # not translated yet
            pairs = [(s.get("de", "").strip(), s.get("en", "").strip()) for s in raw.get("sentences", [])]
            units.append(Unit(n=n, de=raw["de"].strip(), en=raw["en"].strip(), part=part,
                              explain_en=raw.get("explain_en", ""), words=raw.get("words", []),
                              sentence_pairs=[(d, e) for d, e in pairs if d and e]))
        if not any(u.kind == "text" for u in units):
            content.problems.append(f"{path.name}: no translated units")
            continue
        content.books.append(Book(
            id=data.get("id", path.stem), title=data.get("title", path.stem),
            author=data.get("author", ""), year=data.get("year", ""), level=data.get("level", ""),
            intro_en=data.get("intro_en", ""), units=units, total_parts=part,
            short_title=data.get("short_title") or _shorten(data.get("title", path.stem)),
        ))
    for path in sorted(verbs_dir.glob("*.json")):
        data = _load_json(path, content.problems) or {}
        for raw in data.get("verbs", []):
            try:
                verb = Verb(inf=raw["inf"], en=raw["en"], past=raw["past"], perfect=raw["perfect"],
                            alt=_as_list(raw.get("alt")))
            except (KeyError, TypeError):
                content.problems.append(f"{path.name}: bad verb entry {raw!r:.60}")
                continue
            content.verbs.setdefault(verb.inf, verb)
    index_verbs(content)
    reading_words(content)
    return content


_HELPERS = {"hat", "habe", "hast", "haben", "habt", "hatte", "hattest", "hatten", "hattet", "ist", "bin", "bist",
            "sind", "seid", "war", "warst", "waren", "wart", "wäre", "wären", "hätte", "hätten"}


def index_verbs(content: Content) -> None:
    """Find every sentence in the books that uses a past or perfect form of a listed verb.
    Past forms must match exactly (lowercase, so "Schloss" the castle isn't "schloss" the verb);
    participles may have a separable prefix in front: "angekommen" is a form of kommen."""
    past = {form: (v.inf, person) for v in content.verbs.values() for person, form in enumerate(v.past_forms)}
    # A participle that looks like its own infinitive (vergessen, bekommen, gefallen) can't tell "sie vergessen"
    # from "hat vergessen", so those verbs are found by their past forms only.
    participles = {v.participle: v.inf for v in content.verbs.values() if v.participle != v.inf}
    ge_participles = [(p, inf) for p, inf in participles.items() if p.startswith("ge")]
    for book in content.books:
        for unit in book.units:
            if unit.kind != "text":
                continue
            for sentence in sentences(unit.de):
                tokens = re.findall(r"\w+", sentence)
                lower = {t.lower() for t in tokens}
                helper = bool(lower & _HELPERS)  # "hat verloren": perfect, not "wir verloren"
                seen = set()
                for i, token in enumerate(tokens):
                    word = token.lower() if i == 0 else token
                    perfect = participles.get(word) or (
                        next((inf for part, inf in ge_participles if word.endswith(part) and len(word) - len(part) <= 5),
                             None) if "ge" in word[1:] and word[0].islower() else None)
                    # a du/ihr form only right next to du/ihr: "schlicht" is an adjective, "ihr schlicht" a verb
                    next_to = {tokens[j] for j in (i - 1, i + 1) if 0 <= j < len(tokens)}
                    in_past = word in past and (past[word][1] in (0, 2) or bool(next_to & {"du", "ihr", "Du"}))
                    hit = None
                    # "verloren" alone is usually the participle/adjective; the past only with "wir"
                    if perfect and (helper or not in_past or "wir" not in lower):
                        hit = (perfect, word, "perfect")
                    elif in_past:
                        hit = (past[word][0], word, "past")
                    if hit and (hit[0], hit[2]) not in seen:
                        seen.add((hit[0], hit[2]))
                        content.verb_hits.setdefault(hit[0], []).append(
                            VerbHit(book.id, unit.n, sentence, hit[1], hit[2]))


ARTICLES = ("der ", "die ", "das ")


def words_in_reach(content: Content, profile_data: dict) -> set[str]:
    """Words the kid can meet now: the word lists, plus key words of paragraphs already read
    (and any word already practised). Key words of paragraphs still ahead aren't counted yet."""
    ids = {wid for wid, w in content.words.items() if w.bank != READING}
    for book in content.books:
        next_n = profile_data["books"].get(book.id, {}).get("next", 1)
        for unit in book.units:
            if unit.kind == "text" and unit.n < next_n:
                ids.update(unit.word_ids)
    ids.update(wid for wid in profile_data["vocab"] if wid in content.words)
    return ids


def _german_options(de: str) -> list[str]:
    """"der/die Angestellte" -> der Angestellte, die Angestellte; "die Neugierde / die Neugier" -> both;
    "Angst haben/bekommen" -> Angst haben, Angst bekommen. The first is shown, all are accepted."""
    if " / " in de:
        return [o.strip() for o in de.split(" / ") if o.strip()]
    words = de.split()
    for i, w in enumerate(words):
        if "/" in w.strip("/"):
            return [" ".join(words[:i] + [alt] + words[i + 1:]) for alt in w.split("/") if alt]
    return [de]


def key_word(raw: dict) -> tuple[list[str], str, list[str]]:
    """(German options, plural, English answers) of a paragraph key word like
    {"de": "der Staatsanwalt, die Staatsanwälte", "en": "to light (a candle, fire); to kindle"}."""
    de, _, plural = str(raw.get("de", "")).partition(", ")
    if plural and not plural.startswith(ARTICLES):  # "etwas, jemand": not a plural
        de, plural = str(raw["de"]), ""
    en = [e.strip() for e in re.split(r"[,;](?![^()]*\))", str(raw.get("en", ""))) if e.strip()]
    return _german_options(de.strip()), plural.strip(), en


def reading_words(content: Content) -> None:
    """Turn each paragraph's key words into practice words (unit.word_ids). A word already in the bank
    with the same meaning is reused, so it isn't learned twice."""
    by_german: dict[str, list[tuple[set[str], str]]] = {}
    for w in content.words.values():
        key, meanings = meaning_key(w.de, w.en)
        by_german.setdefault(key, []).append((meanings, w.id))
    for book in content.books:
        for unit in book.units:
            for raw in unit.words:
                options, plural, en = key_word(raw)
                de = options[0] if options else ""
                if not de or not en:
                    continue
                key, meanings = meaning_key(de, en)
                wid = next((other for m, other in by_german.get(key, []) if m & meanings), None)
                if wid is None:
                    wid = f"{READING}.{book.id}.{key}"
                    if wid in content.words:  # same German, another meaning in the same book
                        wid += f".{unit.n}"
                    pos = ("noun" if de.lower().startswith(ARTICLES)
                           else "verb" if all(e.startswith("to ") for e in en) else "other")
                    content.words[wid] = Word(id=wid, bank=READING, de=de, en=en, pos=pos, topic=book.short_title,
                                              de_alt=options[1:], plural=plural, note=str(raw.get("note", "")))
                    by_german.setdefault(key, []).append((meanings, wid))
                if wid not in unit.word_ids:
                    unit.word_ids.append(wid)
                word = content.words[wid]
                if not word.story_de and (sentence := story_sentence(de, unit.de, word.pos, word.plural)
                                          or _verb_sentence(content, de, word.pos, book, unit)):
                    word.story_de, word.story_from = sentence, book.short_title


def _verb_sentence(content: Content, de: str, pos: str, book: Book, unit: Unit) -> str:
    """For a key word that is an irregular verb, maybe with a prefix (aufbrechen -> "brach ... auf"), the sentence
    of this paragraph that uses one of its forms. The prefix and any other words (alt aussehen) must be there too."""
    if pos == "noun":
        return ""
    tokens = [t for t in normalize(de).split() if t not in _NOT_THE_WORD]
    if not tokens:
        return ""
    last, others = tokens[-1], tokens[:-1]
    for inf in sorted(content.verb_hits, key=len, reverse=True):
        base = normalize(inf)
        if not last.endswith(base):
            continue
        prefix = last[: -len(base)]
        for hit in content.verb_hits[inf]:
            if hit.book_id != book.id or hit.unit_n != unit.n:
                continue
            words = normalize(hit.sentence).split()
            if all(t in words for t in others) and (
                    not prefix or prefix in words or prefix + normalize(hit.form) in words):
                return trim_around(hit.sentence, hit.form)
        return ""
    return ""


# End of a sentence: . ! ? … then maybe closing quote marks (Tucholsky writes ". . . «" with a space),
# then a space and something that starts a sentence. « and ‹ only ever close a quote here.
_SENTENCE_END = re.compile(r"[.!?…]+(?:\s?[“”\"»«’›‹])*\s+(?=[„\"»‚›(–A-ZÄÖÜ-])")
_ABBREVIATIONS = {"dr", "nr", "st", "hr", "fr", "usw", "bzw", "ca", "vgl", "ggf"}


_MONTHS = ("Januar", "Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
           "Oktober", "November", "Dezember")


def sentences(text: str) -> list[str]:
    """Split German text into sentences. "z. B.", "Dr." and dates like "am 17. März" don't end one;
    a line break always does; a bit of punctuation on its own ("–", "«") joins the sentence before."""
    out: list[str] = []

    def add(piece: str) -> None:
        if out and not re.search(r"[^\W\d_]", piece):
            out[-1] += " " + piece
        elif piece:
            out.append(piece)

    for line in text.splitlines():
        start = 0
        for m in _SENTENCE_END.finditer(line):
            last = re.search(r"(\w+)$", line[start:m.start()])
            if line[m.start()] == "." and last and (len(last.group(1)) == 1
                                                    or last.group(1).lower() in _ABBREVIATIONS
                                                    or last.group(1).isdigit() and line[m.end():].startswith(_MONTHS)):
                continue
            add(line[start:m.end()].strip())
            start = m.end()
        add(line[start:].strip())
    return out


_QUOTES = {"de": [("„", "“"), ("»", "«"), ("‚", "‘"), ("›", "‹"), ('"', '"')],
           "en": [("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")]}
_EDGE = " \t–—-.,;:…"


def _is_apostrophe(text: str, i: int) -> bool:
    """don't, don’t, Mendel's (a letter on both sides) and the Skowronneks' shop (s' then a space)."""
    before = text[i - 1] if i > 0 else " "
    after = text[i + 1] if i < len(text) - 1 else " "
    return before.isalpha() and (after.isalpha() or (before == "s" and after == " "))


def balance_quotes(text: str, lang: str = "de") -> str:
    """A sentence cut out of a longer quote can have only half of its quote marks. A stray mark at the very
    start or end is dropped (the quoted part isn't in this sentence); otherwise the missing partner is added."""
    for open_q, close_q in _QUOTES[lang]:
        stack: list[int] = []
        stray_close: list[int] = []
        for i, ch in enumerate(text):
            if ch not in (open_q, close_q):
                continue
            if ch in "'’" and _is_apostrophe(text, i) and not (stack and text[i - 1] == "s"
                                                               and not text[i + 1:i + 2].isalpha()):
                continue
            if open_q == close_q:  # straight quotes: opening after a space (or at the start) and before a word
                opening = (i == 0 or text[i - 1] in " (–—-\n") and i + 1 < len(text) and not text[i + 1].isspace()
            else:
                opening = ch == open_q
            if opening:
                stack.append(i)
            elif stack:
                stack.pop()
            else:
                stray_close.append(i)
        drop = {i for i in stray_close if not text[:i].strip(_EDGE)} | {i for i in stack if not text[i + 1:].strip(_EDGE)}
        prefix = open_q if any(i not in drop for i in stray_close) else ""
        suffix = close_q if any(i not in drop for i in stack) else ""
        text = prefix + "".join(ch for i, ch in enumerate(text) if i not in drop).strip() + suffix
    return text


STORY_WORDS = 24  # longer book sentences are cut down to the part around the word


def bare_word(word: str) -> str:
    """A word without punctuation around it or a spoken "'s" (war's -> war), lowercase."""
    core = word.strip(".,;:!?»«„“”\"'‚‘’›‹()[]–—-…")
    for ending in ("'s", "’s"):
        if core.endswith(ending):
            core = core[: -len(ending)]
    return core.lower()


def trim_around(sentence: str, form: str) -> str:
    """The sentence, or about STORY_WORDS words of it around the first word containing `form`."""
    words = sentence.split()
    if len(words) <= STORY_WORDS:
        return balance_quotes(sentence)
    hit = next((i for i, w in enumerate(words) if bare_word(w) == form.lower()), 0)
    start = max(0, min(hit - STORY_WORDS // 2, len(words) - STORY_WORDS))
    part = " ".join(words[start:start + STORY_WORDS])
    return balance_quotes(("… " if start else "") + part + (" …" if start + STORY_WORDS < len(words) else ""))


_NOT_THE_WORD = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "sich",
                 "etwas", "jemand", "jemanden", "jemandem", "jdm", "jdn", "etw", "jmd", "auf", "mit", "von",
                 "ueber", "fuer", "aus", "nach", "bei", "zum", "zur", "und", "oder"}


_NOUN_ENDINGS = ("", "s", "es", "e", "en", "n", "er", "ern", "ns")
_VERB_ENDINGS = ("", "e", "st", "est", "t", "et", "en", "te", "test", "ten", "tet", "end", "ende", "enden", "ender")
_OTHER_ENDINGS = ("", "e", "er", "es", "en", "em", "ere", "eren", "erer", "eres", "erem", "ste", "sten", "ster",
                  "stes", "stem", "este", "esten")


@lru_cache(maxsize=None)
def _normalized_sentences(text: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((s, tuple(normalize(w) for w in s.split())) for s in sentences(text))


def _uses_word(word: str, key: str, pos: str, plural: str) -> bool:
    """Is `word` (normalised) a form of `key`? Staatsanwalt ~ Staatsanwälte, strafen ~ strafte, müde ~ müden,
    but not Kleid ~ kleine or meinen ~ meinem."""
    if pos == "noun":
        return any(word == stem + e for stem in {key, plural} if stem for e in _NOUN_ENDINGS)
    if pos == "verb":
        stem = key[:-2] if key.endswith("en") else key[:-1] if key.endswith("n") else key
        return (word.startswith(stem) and word[len(stem):] in _VERB_ENDINGS) or word in {
            f"ge{stem}t", f"ge{stem}et", f"ge{stem}en"}
    return word.startswith(key) and word[len(key):] in _OTHER_ENDINGS


def story_sentence(de: str, text: str, pos: str = "other", plural: str = "") -> str:
    """The first sentence of text that uses the word, or "". A long sentence is cut to about STORY_WORDS
    words around the word. For a phrase ("einen Blick werfen auf") its longest word is looked for."""
    tokens = [t for t in normalize(de).split() if t not in _NOT_THE_WORD and len(t) >= 3]
    if not tokens:
        return ""
    if len(tokens) > 1:  # a phrase: its longest word, with a short ending at most
        key = max(tokens, key=len)
        matches = lambda w: w.startswith(key[:-1]) and len(w) - len(key) <= 2  # noqa: E731
    else:
        key = tokens[0]
        plural_key = normalize(plural).split()[-1] if plural.strip() and plural != "—" else ""
        matches = lambda w: _uses_word(w, key, pos, plural_key)  # noqa: E731
    for sentence, words in _normalized_sentences(text):
        hits = [i for i, w in enumerate(words) if matches(w)]
        if not hits:
            continue
        parts = sentence.split()
        if len(parts) <= STORY_WORDS:
            return balance_quotes(sentence)
        start = max(0, min(hits[0] - STORY_WORDS // 2, len(parts) - STORY_WORDS))
        part = " ".join(parts[start:start + STORY_WORDS])
        return balance_quotes(("… " if start else "") + part + (" …" if start + STORY_WORDS < len(parts) else ""))
    return ""


def words_sharing_english(content: Content, word: Word) -> list[Word]:
    """Other bank words with an overlapping English meaning (wissen/kennen for 'to know')."""
    mine = set().union(*(english_forms(e) for e in word.en))
    return [w for w in content.words.values()
            if w.id != word.id and mine & set().union(*(english_forms(e) for e in w.en))]
