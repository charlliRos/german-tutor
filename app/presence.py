"""Who else is practising on this Wi-Fi? Finding each other, sharing today's results, and duel challenges.

Reliable, not fast: every running app announces its whole state every ANNOUNCE_EVERY seconds (one small
UDP packet, broadcast AND sent straight to the addresses of kids met before, for Wi-Fi that blocks
broadcasts): the kid's name, what they're doing, the results of the last HISTORY_DAYS days, and an open
challenge or the answer to one. The same state is sent again and again, so a lost packet never matters,
and the results each app has received are kept in the kid's profile: when the two apps are next open at
the same time, the news catches up ("While you were away: Ben did a warm-up on Tue 16 Sep…").
Only local-network senders are listened to. News is shown at the top of the next screen (ui.NEWS),
never in the middle of a question. Switch it all off with "share_on_wifi": false in config.json.
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
MAX_PACKET = 16384
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

    def remember(self, friends: dict, addresses: list[str]) -> None:
        """What the profile kept from earlier: the others' results and their computers' addresses."""
        with self._lock:
            self.friends = {name: dict(days) for name, days in friends.items() if isinstance(days, dict)}
            self.addresses = [a for a in addresses if isinstance(a, str) and lan.local_address(a)][:MAX_ADDRESSES]

    def keep(self) -> tuple[dict, list[str]]:
        """What to keep in the profile: the others' results (last KEEP_DAYS days) and their addresses."""
        first = date_minus_str(self.today.get("date", ""), KEEP_DAYS)
        with self._lock:
            friends = {name: {d: r for d, r in days.items() if d >= first} for name, days in self.friends.items()}
            return friends, list(self.addresses)

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
                    "reply": self.reply}

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
                self.receive(data, ip)

    def receive(self, data: bytes, ip: str) -> None:
        """Take in one announcement (anything malformed is ignored)."""
        try:
            m = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return
        if not isinstance(m, dict) or m.get("app") != APP or m.get("v") != VERSION:
            return
        peer_id, name = m.get("id"), m.get("name")
        if not isinstance(peer_id, str) or peer_id == self.id or not isinstance(name, str) or not name.strip():
            return
        name = name.strip()[:30]
        days = m.get("days") if isinstance(m.get("days"), dict) else {}
        days = {d: day for d, raw in list(days.items())[:HISTORY_DAYS + 1]
                if isinstance(d, str) and len(d) == 10 and (day := _clean_day(raw))}
        streak = m.get("streak") if isinstance(m.get("streak"), int) and not isinstance(m.get("streak"), bool) else 0
        with self._lock:
            if ip not in self.addresses and not ip.startswith("127."):
                self.addresses = [ip, *self.addresses][:MAX_ADDRESSES]
            self._news_about(name, days, streak)
            if m.get("status") == "offline":
                self.peers.pop(peer_id, None)
                return
            self.peers[peer_id] = {"name": name, "status": str(m.get("status", ""))[:40],
                                   "today": days.get(self.today.get("date"), {}),
                                   "ip": ip, "duel_port": m.get("duel_port", lan.PORT), "seen": time.monotonic(),
                                   "reply": m.get("reply") if isinstance(m.get("reply"), dict) else None}
            invite = m.get("invite") if isinstance(m.get("invite"), dict) else None
            if invite and invite.get("to") == self.id and isinstance(invite.get("id"), str) \
                    and invite["id"] not in self.invites and invite["id"] not in self._answered:
                port = m.get("duel_port")
                self.invites[invite["id"]] = {"from": peer_id, "name": name, "ip": ip,
                                              "port": port if isinstance(port, int) else lan.PORT,
                                              "until": time.time() + INVITE_SECONDS}
                self.news.append(f"{name} challenges you to a duel! Go to the menu and choose 8 to accept.")

    def _news_about(self, name: str, days: dict, streak: int) -> None:
        """Compare their days with what we knew (kept in the profile): news only for what's new."""
        today = self.today.get("date", "")
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
