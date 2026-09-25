"""Coverage: how many of a text's words a kid knows (docs/LEARNING_DESIGN.md 2.3).

Reading helps when about 95–98% of the words are known. A book is opened when its next paragraph is covered
well enough: at 95% it's simply open; between 90 and 95% it opens and the missing words are taught first
(they go to the front of the next warm-up's new words); under 90% it stays locked, with the count of words to
go. Books already started stay open. A word counts as known from box 2 (seen and recalled once), and the
most common function words (und, ich, ist …) always count.

Words are matched by their forms: nouns with their plural and case endings, verbs with their endings and
past forms, adjectives with their endings (the same rules as content.story_sentence). Names are words that
aren't in the word bank and appear with a capital letter in at least NAME_UNITS paragraphs of the book.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .answers import normalize
from .content import _NOT_THE_WORD, _NOUN_ENDINGS, _OTHER_ENDINGS, _VERB_ENDINGS, Book, person_forms

OPEN, TEACH = 0.95, 0.90
KNOWN_BOX = 2
FUNCTION_RANK = 100      # the 100 most common everyday words always count as known
FUNCTION_FORMS = 150     # and the 150 most common word forms of spoken German (ich, einen, mit, ist …)
NAME_UNITS = 3
FREQUENCY_FILE = Path(__file__).resolve().parent.parent / "tools" / "data" / "de_frequency_top15k.txt"
CONTRACTIONS = {"ins", "im", "am", "vom", "zum", "zur", "beim", "ans", "aufs", "ums", "durchs", "fuers"}
# Present-tense forms the ending rules can't make (modal verbs, sein, haben, werden, wissen, nehmen …)
IRREGULAR_PRESENT = {
    "sein": "bin bist ist sind seid", "haben": "habe hast hat habt", "werden": "werde wirst wird werdet",
    "koennen": "kann kannst koennt", "muessen": "muss musst muesst", "duerfen": "darf darfst duerft",
    "wollen": "will willst wollt", "sollen": "soll sollst sollt", "moegen": "mag magst moegt",
    "wissen": "weiss weisst wisst", "nehmen": "nimmst nimmt", "geben": "gibst gibt", "treten": "trittst tritt",
    "essen": "isst", "lesen": "liest", "sehen": "siehst sieht", "helfen": "hilfst hilft", "sprechen": "sprichst spricht",
    "treffen": "triffst trifft", "werfen": "wirfst wirft", "vergessen": "vergisst", "laufen": "laeufst laeuft",
}
PREFIXES = ("zurück", "zusammen", "weiter", "vorbei", "heraus", "herein", "hinaus", "fest", "fort", "frei", "los",
            "weg", "auf", "aus", "ein", "mit", "nach", "vor", "zu", "an", "ab", "bei", "her", "hin", "um", "dar")


@dataclass
class Coverage:
    share: float
    unknown: list[str] = field(default_factory=list)   # bank word ids not known yet, most common first
    unmatched: list[str] = field(default_factory=list)  # words the bank doesn't have (not names)

    @property
    def state(self) -> str:
        return "open" if self.share >= OPEN else "teach" if self.share >= TEACH else "locked"


def _verb_forms(key: str) -> set[str]:
    stem = key[:-2] if key.endswith("en") else key[:-1] if key.endswith("n") else key
    forms = {stem + e for e in _VERB_ENDINGS} | {f"ge{stem}t", f"ge{stem}et", f"ge{stem}en", key}
    for a, b in (("a", "ae"), ("au", "aeu"), ("o", "oe"), ("e", "i"), ("e", "ie")):  # fährt, läuft, gibt, sieht
        if a in stem:
            changed = stem[::-1].replace(a[::-1], b[::-1], 1)[::-1]
            forms |= {changed + "st", changed + "t", changed}
    return forms


def _forms(word) -> set[str]:
    tokens = normalize(word.de).split()
    tokens = [t for t in tokens if t not in _NOT_THE_WORD] or tokens[-1:]
    if len(tokens) != 1:
        return set()  # phrases are left out: their words are counted one by one
    key = tokens[0]
    if word.pos == "noun":
        plural = normalize(word.plural).split()[-1] if word.plural.strip() and word.plural != "—" else ""
        return {stem + e for stem in {key, plural} if stem for e in _NOUN_ENDINGS}
    if word.pos == "verb":
        forms = _verb_forms(key)
        prefix = next((p for p in PREFIXES if key.startswith(p) and len(key) > len(p) + 3), "")
        if prefix:  # separable: "wachte … auf" is aufwachen; "aufgewacht", "aufzuwachen"
            base = key[len(prefix):]
            base_stem = base[:-2] if base.endswith("en") else base[:-1] if base.endswith("n") else base
            forms |= _verb_forms(base) | {f"{prefix}ge{base_stem}t", f"{prefix}ge{base_stem}en", f"{prefix}zu{base}"}
        return forms
    return {key + e for e in _OTHER_ENDINGS}


def _function_forms() -> frozenset[str]:
    try:
        lines = FREQUENCY_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    forms = [normalize(line.split()[0]) for line in lines if line and not line.startswith("#")]
    return frozenset(forms[:FUNCTION_FORMS])


FUNCTION_WORDS = _function_forms() | CONTRACTIONS


def _lookup(index: dict, token: str) -> frozenset[str] | None:
    """The word ids for a token; a compound (Klassenlehrerin, Fischbrötchen) falls back to its last part,
    which carries the meaning and the gender in German."""
    ids = index.get(token)
    if ids or len(token) < 8:
        return ids
    for i in range(3, len(token) - 3):
        head = token[i:]
        if head in index:
            return index[head]
    return None


_CACHE: dict[int, tuple] = {}  # id(content) -> (content, form index, {book id: names})


def _cached(content) -> tuple:
    hit = _CACHE.get(id(content))
    if hit is None or hit[0] is not content:
        _CACHE.clear()
        hit = _CACHE[id(content)] = (content, _build_index(content), {})
    return hit


def _index(content) -> dict[str, frozenset[str]]:
    return _cached(content)[1]


def _build_index(content) -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {}
    for w in content.words.values():
        for form in _forms(w):
            index.setdefault(form, set()).add(w.id)
    by_de = {normalize(w.de): w.id for w in content.words.values() if w.pos == "verb"}
    for inf, forms in IRREGULAR_PRESENT.items():
        if (wid := by_de.get(inf)):
            for form in forms.split():
                index.setdefault(form, set()).add(wid)
    for verb in content.verbs.values():  # irregular forms: ging, gegangen, gingst …
        wid = by_de.get(normalize(verb.inf))
        if wid:
            for form in [*person_forms(verb.past), verb.participle, *verb.alt]:
                for token in normalize(form).split():
                    index.setdefault(token, set()).add(wid)
    return {form: frozenset(ids) for form, ids in index.items()}


def _tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if len(t) >= 2 and not t.isdigit()]


def names(book: Book, content) -> frozenset[str]:
    """Words of the book the bank doesn't know that are written with a capital in several paragraphs."""
    known = _cached(content)[2]
    if book.id not in known:
        known[book.id] = _names(book, _index(content))
    return known[book.id]


def _names(book: Book, index: dict) -> frozenset[str]:
    seen: dict[str, int] = {}
    for unit in book.units:
        if unit.kind != "text":
            continue
        capital = {normalize(w) for w in re.findall(r"\b[A-ZÄÖÜ][\wäöüß]+", unit.de)}
        for token in capital:
            if token not in index and token not in FUNCTION_WORDS:
                seen[token] = seen.get(token, 0) + 1
    return frozenset(t for t, n in seen.items() if n >= NAME_UNITS)


def text_coverage(content, vocab: dict, text: str, skip: frozenset[str] = frozenset()) -> Coverage:
    index = _index(content)
    words = content.words
    distinct = [t for t in dict.fromkeys(_tokens(text)) if t not in skip]
    if not distinct:
        return Coverage(1.0)
    known, unknown, unmatched = 0, {}, []
    for token in distinct:
        if token in FUNCTION_WORDS:
            known += 1
            continue
        ids = _lookup(index, token)
        if not ids:
            unmatched.append(token)
            continue
        if any(vocab.get(i, {}).get("box", 0) >= KNOWN_BOX or words[i].rank <= FUNCTION_RANK for i in ids):
            known += 1
        else:
            best = min(ids, key=lambda i: (words[i].rank, i))
            unknown[best] = words[best].rank
    return Coverage(known / len(distinct), sorted(unknown, key=unknown.get), unmatched)


def book_coverage(content, vocab: dict, book: Book, next_n: int) -> Coverage | None:
    """Coverage of the book's next German paragraph (None if the book is finished)."""
    unit = book.next_unit(next_n)
    while unit is not None and unit.kind != "text":
        unit = book.next_unit(unit.n + 1)
    return None if unit is None else text_coverage(content, vocab, unit.de, names(book, content))
