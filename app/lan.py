"""Two computers on the same Wi-Fi: one TCP connection, one JSON message per line.

Only the networking lives here; the game is in duel.py. Connections are only accepted from local
network addresses (192.168.x.x, 10.x.x.x, …): this is for two kids side by side, never the internet.
"""
from __future__ import annotations

import ipaddress
import json
import queue
import socket
import threading
import time
import unicodedata

PORT = 50505
PROTOCOL = 1
MAX_LINE = 1 << 20          # 1 MB: a challenge with its words fits easily
MAX_BAD_MESSAGES = 20       # more broken lines than this: it isn't our app on the other end
CLOSED = "_closed"          # the message the reader puts in the queue when the connection ends


class LanError(Exception):
    """Something the player should be told in plain words (can't connect, not on the local network…)."""


def clean_text(value, limit: int) -> str:
    """Text from another computer, safe to show: no control or formatting characters (they could move the
    cursor, clear the screen or reverse text), spaces tidied, cut to `limit`. Not a string: ''."""
    if not isinstance(value, str):
        return ""
    text = "".join(c if unicodedata.category(c)[0] != "C" else " " for c in value[: limit * 4])
    return " ".join(text.split())[:limit]


def parse(data: bytes):
    """JSON from another computer, or None. Deeply nested junk raises RecursionError, not ValueError:
    anything that isn't valid JSON is simply ignored."""
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def local_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def my_ip() -> str:
    """This computer's address on the local network (what the other player types), best guess."""
    for probe in ("192.168.0.1", "10.0.0.1", "172.16.0.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9))  # UDP: nothing is sent, it only picks the right network card
                ip = s.getsockname()[0]
                if local_address(ip) and not ip.startswith("127."):
                    return ip
        except OSError:
            continue
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


class Connection:
    """A connected peer. Messages arrive in `inbox` (a queue of dicts) from a background thread;
    a {"type": CLOSED, "reason": …} message comes last when the connection ends."""

    def __init__(self, sock: socket.socket):
        sock.settimeout(None)
        self.sock = sock
        self.inbox: queue.Queue = queue.Queue()
        self.last_heard = time.monotonic()
        self.bad_messages = 0
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def send(self, message: dict) -> bool:
        """False if the connection is gone (the reader reports why)."""
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            self.close()
            return False

    def start_pings(self, every: float = 1.0) -> None:
        """Send a ping every second from a background thread, so the other side knows we're still here
        even while this player is reading a screen (see duel.SILENT_LIMIT)."""
        def loop():
            while not self._closed.wait(every):
                if not self.send({"type": "ping"}):
                    return
        threading.Thread(target=loop, daemon=True).start()

    def _read_loop(self) -> None:
        buffer = b""
        reason = "the other player left"
        try:
            while not self._closed.is_set():
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_LINE and b"\n" not in buffer:
                    reason = "the other computer sent something this app doesn't understand"
                    break
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._handle_line(line)
                if self.bad_messages > MAX_BAD_MESSAGES:
                    reason = "the other computer sent something this app doesn't understand"
                    break
        except OSError:
            reason = "the connection was lost"
        except Exception:  # never let a strange message end the reader silently: the game must hear about it
            reason = "the other computer sent something this app doesn't understand"
        self.close()
        self.inbox.put({"type": CLOSED, "reason": reason})

    def _handle_line(self, line: bytes) -> None:
        if not line.strip():
            return
        message = parse(line)
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            self.bad_messages += 1
            return
        self.last_heard = time.monotonic()
        self.inbox.put(message)

    def receive(self, timeout: float | None = None) -> dict | None:
        """The next message, or None if none arrived in time."""
        try:
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()


class Host:
    """Waits for the other player. Only local-network addresses may connect."""

    def __init__(self, port: int = PORT):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind(("0.0.0.0", port))
        except OSError as exc:
            self.server.close()
            raise LanError(f"Can't open port {port} ({exc.strerror or exc}). Is another game already hosting?") from None
        self.server.listen(1)
        self.server.settimeout(0.5)

    def accept(self) -> Connection | None:
        """A connection from the local network, or None if nobody came in the last half second."""
        try:
            sock, (ip, _) = self.server.accept()
        except socket.timeout:
            return None
        if not local_address(ip):
            sock.close()  # not from the local network: never accepted
            return None
        return Connection(sock)

    def close(self) -> None:
        self.server.close()


def join(ip: str, port: int = PORT, timeout: float = 5.0) -> Connection:
    if not local_address(ip):
        raise LanError(f"{ip} isn't a local network address. Type the address the host's screen shows "
                       "(like 192.168.1.23).")
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
    except ConnectionRefusedError:
        raise LanError(f"Nobody is hosting at {ip}. Start 'Host' on the other computer first.") from None
    except (socket.timeout, TimeoutError):
        raise LanError(f"No answer from {ip}. Are both computers on the same Wi-Fi? "
                       "On the host, Windows may ask to allow Python on private networks: click Allow.") from None
    except OSError as exc:
        raise LanError(f"Can't reach {ip} ({exc.strerror or exc}).") from None
    return Connection(sock)
