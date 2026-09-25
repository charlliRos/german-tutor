"""Who else is practising on this Wi-Fi? Finding each other, sharing today's results, and duel challenges.

Reliable, not fast: every running app announces its whole state every ANNOUNCE_EVERY seconds (one small
UDP packet, broadcast AND sent straight to the addresses of kids met before, for Wi-Fi that blocks
broadcasts): the kid's name, what they're doing, the results of the last HISTORY_DAYS days, and an open
challenge or the answer to one. The same state is sent again and again, so a lost packet never matters,
and the results each app has received are kept in the kid's profile: when the two apps are next open at
the same time, the news catches up ("While you were away: Ben did a warm-up on Tue 16 Sep…").
Only local-network senders are listened to. News is shown at the top of the next screen (ui.NEWS),
never in the middle of a question. Each kid is asked once whether to share (menu 8 changes it); a parent can
decide for everyone with "share_on_wifi": true / false in config.json.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid

from . import lan

PORT = 50506
APP = "gtutor"
VERSION = 2  # apps with a different version don't listen to each other: update both
ANNOUNCE_EVERY = 5.0   # seconds: no hurry, the same state is sent again and again
GONE_AFTER = 20.0      # seconds without an announcement: that player went offline
INVITE_SECONDS = 300   # a challenge waits this long for an answer
HISTORY_DAYS = 7       # days of results in every announcement (and kept by the others)
KEEP_DAYS = 14         # days of the others' results kept in the profile
MAX_ADDRESSES = 8      # other computers remembered, to send to directly
MAX_PACKET = 65507     # the most UDP allows: a few challenges with their words fit easily
CHALLENGE_DAYS = 7     # an asynchronous challenge can be played for this many days
MAX_SENT_CHALLENGES = 4  # the newest ones go into each announcement
# Limits on what other computers can make this app keep (anyone on the Wi-Fi can send announcements):
MAX_PEERS = 16          # players online at once
MAX_INVITES = 4         # duel challenges waiting
MAX_FRIENDS = 12        # kids whose results are kept (the one heard from longest ago makes room)
MAX_CHALLENGES = 40     # asynchronous challenges kept
MAX_CHALLENGES_PER_KID = 8
FIELDS = ("warmups", "words", "right", "paragraphs", "minutes")


def day_summary(counts: dict) -> dict:
    return {"warmups": counts.get("warmups", 0), "words": counts.get("words", 0), "right": counts.get("right", 0),
            "paragraphs": counts.get("units", 0), "minutes": round(counts.get("seconds", 0) / 60)}


def today_summary(profile, today) -> dict:
    """What the others see of today's practice (streak included)."""
    return {"date": today.isoformat(), **day_summary(profile.day(today)), "streak": profile.streak(today)}


def history(profile, today, days: int = HISTORY_DAYS) -> dict:
    """{date: summary} for the practice days of the last `days` days (today's may be updated separately)."""
    first = date_minus(today, days - 1)
    return {d: day_summary(c) for d, c in profile.data["days"].items()
            if first <= d <= today.isoformat() and (c.get("warmups") or c.get("units"))}


def date_minus(today, days: int) -> str:
    from datetime import timedelta
    return (today - timedelta(days=days)).isoformat()


def date_minus_str(iso: str, days: int) -> str:
    from datetime import date
    try:
        return date_minus(date.fromisoformat(iso), days)
    except ValueError:
        return ""


def weekday(iso: str) -> str:
    from datetime import date
    try:
        return date.fromisoformat(iso).strftime("%a %d %b")
    except ValueError:
        return iso


def _clean_day(raw) -> dict | None:
    """A day's results from another computer: known numbers only, else None."""
    if not isinstance(raw, dict):
        return None
    day = {k: raw.get(k, 0) for k in FIELDS}
    if not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 100000 for v in day.values()):
        return None
    return day


def _clean_answers(raw, count: int) -> list[dict] | None:
    if not isinstance(raw, list) or len(raw) > count:
        return None
    answers = []
    for a in raw:
        if not isinstance(a, dict) or not isinstance(a.get("answer", ""), str) \
                or not isinstance(a.get("seconds"), (int, float)) or isinstance(a.get("seconds"), bool):
            return None
        answers.append({"answer": a.get("answer", "")[:100], "seconds": float(a["seconds"])})
    return answers


def _clean_challenge(raw) -> dict | None:
    """An asynchronous challenge from another computer, checked; None if anything is off."""
    if not isinstance(raw, dict):
        return None
    cid, created = raw.get("id"), raw.get("created")
    if not all(isinstance(x, str) and 0 < len(x) <= 30 for x in (cid, raw.get("from"), raw.get("to"))):
        return None
    sender, to = lan.clean_text(raw["from"], 30), lan.clean_text(raw["to"], 30)
    clean = clean_questions(raw.get("questions"), full=False)
    if not sender or not to or not isinstance(created, str) or clean is None:
        return None
    answers = raw.get("answers") if isinstance(raw.get("answers"), dict) else {}
    kept = {}
    for name in (sender, to):
        if name in answers:
            if (clean_answers := _clean_answers(answers[name], len(clean))) is None:
                return None
            kept[name] = clean_answers
    return {"id": cid, "from": sender, "to": to, "created": created[:10], "questions": clean, "answers": kept}


def clean_questions(raw, full: bool = True) -> list[dict] | None:
    """Duel words from another computer, checked and cleaned (None if anything is off). full: keep what a
    live duel shows too (plural, examples); asynchronous challenges only carry what's needed to check."""
    if not isinstance(raw, list) or not 0 < len(raw) <= 20:
        return None
    clean = []
    for q in raw:
        word = q.get("word") if isinstance(q, dict) else None
        if not isinstance(word, dict) or q.get("direction") not in ("en2de", "de2en") \
                or not isinstance(word.get("de"), str) or not isinstance(word.get("en"), list):
            return None
        de = lan.clean_text(word["de"], 60)
        en = [e for e in (lan.clean_text(x, 60) for x in word["en"][:4]) if e]
        if not de or not en:
            return None
        alt = word.get("de_alt") if isinstance(word.get("de_alt"), list) else []
        checked = {"id": lan.clean_text(word.get("id", ""), 40), "bank": "daily", "de": de, "en": en,
                   "pos": lan.clean_text(word.get("pos", "other"), 10) or "other",
                   "de_alt": [a for a in (lan.clean_text(x, 60) for x in alt[:4]) if a]}
        if full:
            checked.update({k: lan.clean_text(word.get(k, ""), 200) for k in ("plural", "example_de", "example_en")})
        clean.append({"direction": q["direction"], "word": checked})
    return clean


def challenge_score(challenge: dict, name: str) -> int | None:
    """Points for one kid's answers (the live duel's scoring), None if they haven't played yet."""
    from .duel import score  # here, not at the top: duel imports this module
    answers = challenge["answers"].get(name)
    return None if answers is None else score(challenge["questions"], answers)


def challenge_result(challenge: dict, me: str) -> str:
    """"Ben 1180 · you 1240: you win!" (or "" while someone still has to play)."""
    other = challenge["to"] if challenge["from"] == me else challenge["from"]
    mine, theirs = challenge_score(challenge, me), challenge_score(challenge, other)
    if mine is None or theirs is None:
        return ""
    verdict = "a draw!" if mine == theirs else "you win!" if mine > theirs else f"{other} wins!"
    return f"{other} {theirs} · you {mine}: {verdict}"


def describe(name: str, t: dict) -> str:
    """"38 of 40 words right · 2 paragraphs · 14 min · 6 days in a row"."""
    parts = []
    if t.get("words"):
        parts.append(f"{t.get('right', 0)} of {t['words']} words right")
    if t.get("paragraphs"):
        parts.append(f"{t['paragraphs']} paragraph{'s' if t['paragraphs'] != 1 else ''}")
    if t.get("minutes"):
        parts.append(f"{t['minutes']} min")
    if t.get("streak"):
        parts.append(f"{t['streak']} day{'s' if t['streak'] != 1 else ''} in a row")
    return " · ".join(parts) or "just started"


class Presence:
    def __init__(self, name: str, port: int = PORT, duel_port: int = lan.PORT):
        self.id = uuid.uuid4().hex[:10]  # this run of the app
        self.name = name
        self.port = port
        self.duel_port = duel_port
        self.status = "on the menu"
        self.today: dict = {}
        self.invite: dict | None = None     # my open challenge: {"id", "to", "until"}
        self.reply: dict | None = None      # my answer to someone's challenge: {"id", "accept"}
        self.peers: dict[str, dict] = {}    # id -> latest announcement (+ "ip", "seen")
        self.invites: dict[str, dict] = {}  # challenges to me: invite id -> {"from", "name", "ip", "port", "until"}
        self.news: list[str] = []
        self.days: dict[str, dict] = {}         # this kid's last HISTORY_DAYS days of results
        self.friends: dict[str, dict] = {}      # name -> {date: results}, from the others; kept in the profile
        self.addresses: list[str] = []          # other computers met before (sent to directly too)
        self.challenges: dict[str, dict] = {}   # asynchronous challenges with this kid, by id; kept in the profile
        self._answered: set[str] = set()   # challenges already answered (still announced for a while)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.sock: socket.socket | None = None

    # ----- starting and stopping -----

    def start(self) -> str:
        """Start announcing and listening. Returns a problem to show, or ''."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self.port))
            sock.settimeout(0.5)
        except OSError as exc:
            return f"Can't look for other players on the Wi-Fi ({exc.strerror or exc})."
        self.sock = sock
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._announce_loop, daemon=True).start()
        return ""

    def stop(self) -> None:
        self._stop.set()
        if self.sock:
            self.status = "offline"
            self._announce()
            self.sock.close()

    # ----- what this app tells the others -----

    def set_status(self, status: str) -> None:
        if status != self.status:
            self.status = status
            self._announce()

    def set_today(self, summary: dict, days: dict | None = None) -> None:
        """Today's results (with "date" and "streak"), and the last days' (see history())."""
        days = dict(days or {})
        days[summary["date"]] = {k: summary.get(k, 0) for k in FIELDS}
        if summary != self.today or days != self.days:
            self.today, self.days = summary, days
            self._announce()

    def remember(self, friends: dict, addresses: list[str], challenges: dict | None = None) -> None:
        """What the profile kept from earlier: the others' results, their computers' addresses, challenges."""
        with self._lock:
            self.friends = {name: dict(days) for name, days in list(friends.items())[:MAX_FRIENDS]
                            if isinstance(days, dict)}
            self.addresses = [a for a in addresses if isinstance(a, str) and lan.local_address(a)][:MAX_ADDRESSES]
            self.challenges = {cid: c for cid, raw in (challenges or {}).items() if (c := _clean_challenge(raw))}

    def keep(self) -> tuple[dict, list[str], dict]:
        """What to keep in the profile: the others' results (last KEEP_DAYS days), their addresses, challenges."""
        first = date_minus_str(self.today.get("date", ""), KEEP_DAYS)
        with self._lock:
            friends = {name: {d: r for d, r in days.items() if d >= first} for name, days in self.friends.items()}
            challenges = {cid: c for cid, c in self.challenges.items() if c["created"] >= first}
            return friends, list(self.addresses), challenges

    # ----- asynchronous challenges: each kid plays the same words when they like -----

    def add_challenge(self, challenge: dict) -> None:
        with self._lock:
            self.challenges[challenge["id"]] = challenge
        self._announce()

    def record_answers(self, challenge_id: str, answers: list[dict]) -> None:
        with self._lock:
            challenge = self.challenges.get(challenge_id)
            if challenge is not None and self.name not in challenge["answers"]:
                challenge["answers"][self.name] = answers
        self._announce()

    def my_challenges(self) -> list[dict]:
        """Challenges with this kid, newest first (copies)."""
        with self._lock:
            return sorted((json.loads(json.dumps(c)) for c in self.challenges.values()
                           if self.name in (c["from"], c["to"])), key=lambda c: c["created"], reverse=True)

    def to_play(self) -> list[dict]:
        """Challenges waiting for this kid, still within CHALLENGE_DAYS."""
        first = date_minus_str(self.today.get("date", ""), CHALLENGE_DAYS)
        return [c for c in self.my_challenges() if self.name not in c["answers"] and c["created"] >= first]

    def _merge_challenge(self, raw) -> None:
        """Take in a challenge from another computer (called with the lock held)."""
        incoming = _clean_challenge(raw)
        if incoming is None or self.name not in (incoming["from"], incoming["to"]):
            return
        other = incoming["to"] if incoming["from"] == self.name else incoming["from"]
        known = self.challenges.get(incoming["id"])
        if known is None:
            if incoming["from"] == self.name or incoming["created"] < date_minus_str(self.today.get("date", ""),
                                                                                     CHALLENGE_DAYS):
                return  # one of mine this profile has forgotten, or run out: nothing to do
            with_them = sum(1 for c in self.challenges.values() if other in (c["from"], c["to"]))
            if len(self.challenges) >= MAX_CHALLENGES or with_them >= MAX_CHALLENGES_PER_KID:
                return  # a flood of challenges: keep what we have
            self.challenges[incoming["id"]] = incoming
            theirs = challenge_score(incoming, other)
            self.news.append(f"{other} challenges you: {len(incoming['questions'])} words"
                             + (f", {other} scored {theirs}. Beat it!" if theirs is not None else ".")
                             + " Play it any time in menu 8.")
            return
        if other in incoming["answers"] and other not in known["answers"]:
            known["answers"][other] = incoming["answers"][other]  # answers are written once, never changed
            result = challenge_result(known, self.name)
            self.news.append(f"{other} played your challenge: {result}" if result
                             else f"{other} played the challenge: your turn! (menu 8)")

    def friend_day(self, name: str, iso: str) -> dict | None:
        with self._lock:
            return dict(self.friends.get(name, {}).get(iso) or {}) or None

    def friends_today(self) -> dict[str, dict]:
        """name -> today's results, for everyone heard from (even if they've gone offline since)."""
        today = self.today.get("date")
        with self._lock:
            return {name: dict(days[today]) for name, days in self.friends.items() if today in days}

    def message(self) -> dict:
        with self._lock:
            invite = dict(self.invite) if self.invite and self.invite["until"] > time.time() else None
            return {"app": APP, "v": VERSION, "id": self.id, "name": self.name, "status": self.status,
                    "today": self.today.get("date"), "streak": self.today.get("streak", 0), "days": self.days,
                    "duel_port": self.duel_port,
                    "invite": {"id": invite["id"], "to": invite["to"]} if invite else None,
                    "reply": self.reply, "challenges": self._challenges_to_send()}

    def _challenges_to_send(self) -> list[dict]:
        """The newest challenges with this kid from the last CHALLENGE_DAYS days (called with the lock held)."""
        first = date_minus_str(self.today.get("date", ""), CHALLENGE_DAYS)
        mine = [c for c in self.challenges.values() if c["created"] >= first and self.name in (c["from"], c["to"])]
        return sorted(mine, key=lambda c: c["created"], reverse=True)[:MAX_SENT_CHALLENGES]

    def _announce(self) -> None:
        if not self.sock or (self._stop.is_set() and self.status != "offline"):
            return
        data = json.dumps(self.message(), ensure_ascii=False).encode("utf-8")
        with self._lock:
            targets = ["255.255.255.255", *self.addresses]
        for target in targets:  # broadcast, and straight to the computers met before
            try:
                self.sock.sendto(data, (target, self.port))
            except OSError:
                pass  # no network right now, or that computer is off: next time

    def _announce_loop(self) -> None:
        while not self._stop.wait(ANNOUNCE_EVERY):
            self._announce()

    # ----- what the others tell us -----

    def _listen(self) -> None:
        while not self._stop.is_set():
            try:
                data, (ip, _) = self.sock.recvfrom(MAX_PACKET)
            except socket.timeout:
                continue
            except OSError:
                return
            if lan.local_address(ip):
                try:
                    self.receive(data, ip)
                except Exception:  # one strange announcement must never stop the listening
                    continue

    def receive(self, data: bytes, ip: str) -> None:
        """Take in one announcement (anything malformed is ignored)."""
        m = lan.parse(data)
        if not isinstance(m, dict) or m.get("app") != APP or m.get("v") != VERSION:
            return
        peer_id, name = m.get("id"), lan.clean_text(m.get("name"), 30)
        if not isinstance(peer_id, str) or not 0 < len(peer_id) <= 40 or peer_id == self.id or not name:
            return
        days = m.get("days") if isinstance(m.get("days"), dict) else {}
        days = {d: day for d, raw in list(days.items())[:HISTORY_DAYS + 1]
                if isinstance(d, str) and len(d) == 10 and (day := _clean_day(raw))}
        streak = m.get("streak") if isinstance(m.get("streak"), int) and not isinstance(m.get("streak"), bool) else 0
        with self._lock:
            if ip not in self.addresses and not ip.startswith("127."):
                self.addresses = [ip, *self.addresses][:MAX_ADDRESSES]
            self._news_about(name, days, streak)
            for raw in m.get("challenges", [])[:MAX_SENT_CHALLENGES] if isinstance(m.get("challenges"), list) else []:
                self._merge_challenge(raw)
            if m.get("status") == "offline":
                self.peers.pop(peer_id, None)
                return
            if peer_id not in self.peers and len(self.peers) >= MAX_PEERS:
                del self.peers[min(self.peers, key=lambda p: self.peers[p]["seen"])]  # the quietest makes room
            self.peers[peer_id] = {"name": name, "status": lan.clean_text(m.get("status", ""), 40),
                                   "today": days.get(self.today.get("date"), {}),
                                   "ip": ip, "duel_port": m.get("duel_port", lan.PORT), "seen": time.monotonic(),
                                   "reply": m.get("reply") if isinstance(m.get("reply"), dict) else None}
            invite = m.get("invite") if isinstance(m.get("invite"), dict) else None
            if invite and invite.get("to") == self.id and isinstance(invite.get("id"), str) \
                    and len(invite["id"]) <= 40 and len(self.invites) < MAX_INVITES \
                    and invite["id"] not in self.invites and invite["id"] not in self._answered:
                port = m.get("duel_port")
                self.invites[invite["id"]] = {"from": peer_id, "name": name, "ip": ip,
                                              "port": port if isinstance(port, int) else lan.PORT,
                                              "until": time.time() + INVITE_SECONDS}
                self.news.append(f"{name} challenges you to a duel! Go to the menu and choose 8 to accept.")

    def _news_about(self, name: str, days: dict, streak: int) -> None:
        """Compare their days with what we knew (kept in the profile): news only for what's new."""
        today = self.today.get("date", "")
        if name not in self.friends and len(self.friends) >= MAX_FRIENDS:
            quietest = min(self.friends, key=lambda n: max(self.friends[n], default=""))
            del self.friends[quietest]  # the kid heard from longest ago makes room
        known = self.friends.setdefault(name, {})
        first_meeting = not known
        missed = []
        for iso in sorted(days):
            if iso > today or iso < date_minus_str(today, HISTORY_DAYS):
                continue  # a computer with a wrong date, or too old
            now, before = days[iso], known.get(iso)
            known[iso] = now
            if iso == today:
                done = [what for what, key in (("a warm-up", "warmups"), ("a new paragraph", "paragraphs"))
                        if now[key] > (before or {}).get(key, 0)]
                if done and before is not None:
                    self.news.append(f"{name} just finished {' and '.join(done)}: "
                                     f"{describe(name, {**now, 'streak': streak})}. Your turn!")
                elif done:
                    self.news.append(f"{name} has practised today already: "
                                     f"{describe(name, {**now, 'streak': streak})}.")
            elif before is None and not first_meeting and (now["warmups"] or now["paragraphs"]):
                missed.append(f"{weekday(iso)}: {describe(name, now)}")
        if missed:
            self.news.append(f"While you were away, {name} practised on " + "; ".join(missed[-3:]) + ".")

    # ----- for the screens -----

    def online(self) -> list[dict]:
        """Players seen in the last GONE_AFTER seconds, with their id."""
        now = time.monotonic()
        with self._lock:
            return sorted(({"id": pid, **p} for pid, p in self.peers.items() if now - p["seen"] < GONE_AFTER),
                          key=lambda p: p["name"].casefold())

    def take_news(self) -> list[str]:
        with self._lock:
            news, self.news = self.news, []
        return news

    def pending_invites(self) -> list[dict]:
        now = time.time()
        with self._lock:
            return [{"id": i, **inv} for i, inv in self.invites.items() if inv["until"] > now]

    # ----- challenges -----

    def challenge(self, peer_id: str) -> str:
        """Challenge a player (the caller then hosts the duel). Returns the challenge id."""
        invite_id = uuid.uuid4().hex[:10]
        with self._lock:
            self.invite = {"id": invite_id, "to": peer_id, "until": time.time() + INVITE_SECONDS}
        self._announce()
        return invite_id

    def challenge_answer(self, invite_id: str) -> bool | None:
        """True / False once the challenged player answered, None while waiting."""
        with self._lock:
            invite = self.invite
            if not invite or invite["id"] != invite_id:
                return None
            peer = self.peers.get(invite["to"])
            reply = peer.get("reply") if peer else None
        if reply and reply.get("id") == invite_id:
            return bool(reply.get("accept"))
        return None

    def cancel_challenge(self) -> None:
        with self._lock:
            self.invite = None
        self._announce()

    def answer(self, invite_id: str, accept: bool) -> dict | None:
        """Answer a challenge. Returns the invite (with the challenger's ip and port) if it still stands."""
        with self._lock:
            invite = self.invites.pop(invite_id, None)
            self._answered.add(invite_id)
            self.reply = {"id": invite_id, "accept": accept}
        self._announce()
        return invite if invite and invite["until"] > time.time() else None
