"""Who else is practising on this Wi-Fi? Finding each other, sharing today's results, and duel challenges.

Every running app announces its state on the local network every ANNOUNCE_EVERY seconds (one small UDP
broadcast): the kid's name, what they're doing, today's results, and an open challenge or the answer
to one. Everything is worked out from those announcements, so nothing depends on a single message
arriving. Only local-network senders are listened to. The news ("Anna just finished a warm-up…") is
collected here and shown at the top of the next screen (ui.NEWS), never in the middle of a question.
Switch it all off with "share_on_wifi": false in config.json.
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
VERSION = 1
ANNOUNCE_EVERY = 2.0   # seconds
GONE_AFTER = 8.0       # seconds without an announcement: that player went offline
INVITE_SECONDS = 120   # a challenge waits this long for an answer
MAX_PACKET = 8192


def today_summary(profile, today) -> dict:
    """What the others see of today's practice."""
    day = profile.day(today)
    return {"date": today.isoformat(), "warmups": day.get("warmups", 0), "words": day.get("words", 0),
            "right": day.get("right", 0), "paragraphs": day.get("units", 0),
            "minutes": round(day.get("seconds", 0) / 60), "streak": profile.streak(today)}


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
        self.seen_today: dict[str, dict] = {}  # name -> their latest results today (kept after they go offline)
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

    def set_today(self, summary: dict) -> None:
        if summary != self.today:
            self.today = summary
            self._announce()

    def message(self) -> dict:
        with self._lock:
            invite = dict(self.invite) if self.invite and self.invite["until"] > time.time() else None
            return {"app": APP, "v": VERSION, "id": self.id, "name": self.name, "status": self.status,
                    "today": self.today, "duel_port": self.duel_port,
                    "invite": {"id": invite["id"], "to": invite["to"]} if invite else None,
                    "reply": self.reply}

    def _announce(self) -> None:
        if not self.sock or (self._stop.is_set() and self.status != "offline"):
            return
        data = json.dumps(self.message(), ensure_ascii=False).encode("utf-8")
        try:
            self.sock.sendto(data, ("255.255.255.255", self.port))
        except OSError:
            pass  # no network right now: try again next time

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
        raw = m.get("today") if isinstance(m.get("today"), dict) else {}
        today = {k: v for k, v in raw.items() if k == "date" and isinstance(v, str)
                 or isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 100000}  # numbers only
        with self._lock:
            before = self.peers.get(peer_id)
            if today.get("date") == self.today.get("date"):
                self.seen_today[name] = today
            if m.get("status") == "offline":
                self.peers.pop(peer_id, None)
                return
            self.peers[peer_id] = {"name": name, "status": str(m.get("status", ""))[:40], "today": today,
                                   "ip": ip, "duel_port": m.get("duel_port", lan.PORT), "seen": time.monotonic(),
                                   "reply": m.get("reply") if isinstance(m.get("reply"), dict) else None}
            try:
                self._news_about(name, before["today"] if before else None, today)
            except (TypeError, ValueError):
                pass  # nonsense numbers from the other computer: no news
            invite = m.get("invite") if isinstance(m.get("invite"), dict) else None
            if invite and invite.get("to") == self.id and isinstance(invite.get("id"), str) \
                    and invite["id"] not in self.invites and invite["id"] not in self._answered:
                port = m.get("duel_port")
                self.invites[invite["id"]] = {"from": peer_id, "name": name, "ip": ip,
                                              "port": port if isinstance(port, int) else lan.PORT,
                                              "until": time.time() + INVITE_SECONDS}
                self.news.append(f"{name} challenges you to a duel! Go to the menu and choose 8 to accept.")

    def _news_about(self, name: str, before: dict | None, now: dict) -> None:
        if now.get("date") != self.today.get("date"):
            return  # another day (a computer with a different date, or just after midnight)
        if before is None or before.get("date") != now.get("date"):
            if now.get("warmups") or now.get("paragraphs"):
                self.news.append(f"{name} has practised today already: {describe(name, now)}.")
            return
        finished = []
        if now.get("warmups", 0) > before.get("warmups", 0):
            finished.append("a warm-up")
        if now.get("paragraphs", 0) > before.get("paragraphs", 0):
            finished.append("a new paragraph")
        if finished:
            self.news.append(f"{name} just finished {' and '.join(finished)}: {describe(name, now)}. Your turn!")

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
