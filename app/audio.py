"""Offline German speech (Piper) plus microphone recording and playback (sounddevice).

Everything degrades gracefully: a missing voice model, speaker or microphone just
switches that feature off and the lessons carry on without it.
"""
from __future__ import annotations

import re
import time

import numpy as np

from .config import VOICES_DIR

SENTENCE_PAUSE = 0.25  # seconds of silence between synthesized sentences
TURN_PAUSE = 0.45      # between two speakers in a conversation
# More speakers from the one German voice, at normal speed: the speech is made this much slower, then played
# this much faster, which raises (or lowers) the pitch. No extra voice to download.
VOICES = {"": 1.0, "high": 1.24, "higher": 1.38, "low": 0.86}
SILENCE_PEAK = 0.02    # recordings quieter than this count as "nothing heard"
QUIET_PEAK = 0.08      # below this the mic works but is set very low


BLOCKED_VOICE = ("Windows blocked the offline German voice (Smart App Control or a school's app policy: one of its "
                 "files isn't signed).")


def blocked(exc: Exception) -> bool:
    """Windows refused to load a file (Smart App Control, Application Control, WDAC)."""
    text = str(exc).lower()
    return "application control" in text or "blocked" in text or "4551" in text


def clean_for_speech(text: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", text)
    for short, full in (("etw.", "etwas"), ("jdm.", "jemandem"), ("jdn.", "jemanden"), ("jmd.", "jemand")):
        text = text.replace(short, full)
    text = text.replace("…", " ").replace("/", ", ")
    return " ".join(text.split())


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or audio.size == 0:
        return audio
    n = int(len(audio) * dst / src)
    return np.interp(np.linspace(0, len(audio), n, endpoint=False),
                     np.arange(len(audio)), audio).astype(np.float32)


def _tidy(audio: np.ndarray, rate: int) -> np.ndarray:
    """Trim silence at both ends and turn the volume up so quiet mics are audible."""
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak < SILENCE_PEAK:
        return np.zeros(0, dtype=np.float32)
    # Loudness per 20 ms window; keep everything between the first and last clearly loud window.
    win = max(rate // 50, 1)
    n = len(audio) // win
    if n >= 3:
        rms = np.sqrt(np.mean(audio[: n * win].reshape(n, win) ** 2, axis=1))
        floor = float(np.percentile(rms, 10))
        loud = np.flatnonzero(rms > max(floor * 3, float(rms.max()) * 0.2))
        if loud.size:  # steady hum or noise has no clearly loud part: keep it all
            pad = int(0.15 * rate)
            audio = audio[max(loud[0] * win - pad, 0): (loud[-1] + 1) * win + pad]
    return (audio * (0.9 / peak)).astype(np.float32)


class Audio:
    def __init__(self, settings: dict, enabled: bool = True):
        self.settings = settings
        self.sd = None
        self.voice = None
        self.sysvoice = None  # the computer's own voice, when the Piper voice can't run (app/sysvoice.py)
        self.has_mic = False
        self.last_peak = 0.0  # loudness of the last raw recording, before volume boost
        self.listener = None  # speech check (app/listen.py): only loaded when there's a mic
        self.problems: list[str] = []
        self._cache: dict[tuple[str, float], tuple[np.ndarray, int]] = {}
        if not enabled:
            self.problems.append("Audio is switched off (--no-audio).")
            return
        self._init_devices()
        if self.sd:
            self._init_voice()
        if self.can_record and settings.get("speech_check", True):
            from . import listen
            self.listener, problem = listen.load()
            if problem:
                self.problems.append(problem)

    @property
    def can_check_speech(self) -> bool:
        return self.listener is not None

    def heard(self, audio: np.ndarray, rate: int) -> str:
        """What the speech checker heard in a recording ('' for nothing)."""
        try:
            return self.listener.transcribe(audio, rate) if self.listener and audio.size else ""
        except Exception:
            return ""

    def _init_devices(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:  # PortAudio missing on Linux raises OSError
            self.problems.append(f"Sound library unavailable ({exc}). Linux: install PortAudio "
                                 "(sudo apt install libportaudio2 / dnf install portaudio / pacman -S portaudio)")
            return
        try:
            sd.query_devices(self.settings.get("output_device"), kind="output")
        except Exception:
            self.problems.append("No speakers or headphones found, so nothing can be read out.")
            return
        self.sd = sd
        try:
            info = sd.query_devices(self.settings.get("input_device"), kind="input")
            self.has_mic = info["max_input_channels"] > 0
        except Exception:
            self.has_mic = False
        if not self.has_mic:
            self.problems.append("No microphone found. You'll say things out loud without recording.")

    def _init_voice(self) -> None:
        """The offline Piper voice; if it can't run here, the computer's own German voice ("voice_engine" in
        config.json: auto, piper or system)."""
        engine = self.settings.get("voice_engine", "auto")
        problem = "" if engine == "system" else self._init_piper()
        if problem and engine == "piper":
            self.problems.append(problem)
        elif problem or engine == "system":
            self._init_system_voice(problem)

    def _init_piper(self) -> str:
        """Load the Piper voice and say a word silently to be sure it runs. '' if it works, else why not."""
        model = VOICES_DIR / f"{self.settings['voice']}.onnx"
        if not model.exists():
            return "The German voice isn't downloaded yet (run: gtutor update)."
        try:
            from piper import PiperVoice
            from piper.config import SynthesisConfig
            self.voice = PiperVoice.load(model)
            self._synthesis_config = SynthesisConfig
            self.synthesize("Hallo", 1.0)  # the speech part only loads now: a blocked file fails here, not mid-lesson
        except Exception as exc:
            self.voice = None
            self._cache.clear()
            return BLOCKED_VOICE if blocked(exc) else f"The offline German voice can't run here ({exc})."
        return ""

    def _init_system_voice(self, piper_problem: str) -> None:
        from . import sysvoice
        try:
            self.sysvoice = sysvoice.open_voice("de")
        except Exception as exc:
            self.problems.append(f"{piper_problem or 'The system voice was chosen in config.json.'} No German system "
                                 f"voice either ({exc}). To get sound, {sysvoice.install_hint()}, then restart the "
                                 "app. Everything else works without sound.")
            return
        if piper_problem:
            self.problems.append(f"{piper_problem} Using the computer's German voice ({self.sysvoice.name}) instead.")

    @property
    def can_speak(self) -> bool:
        return self.sd is not None and (self.voice is not None or self.sysvoice is not None)

    @property
    def can_record(self) -> bool:
        return self.sd is not None and self.has_mic

    def synthesize(self, text: str, length_scale: float, voice: str = "") -> tuple[np.ndarray, int]:
        factor = VOICES.get(voice, 1.0)
        key = (text, length_scale, voice)
        if key not in self._cache and self.voice is None and self.sysvoice is not None:
            audio, rate = self.sysvoice.speak(clean_for_speech(text), 1.0 / (length_scale * factor))
            self._cache[key] = (audio, int(rate * factor))
        if key not in self._cache:
            parts, rate = [], 22050
            config = self._synthesis_config(length_scale=length_scale * factor)
            for chunk in self.voice.synthesize(clean_for_speech(text), config):
                rate = chunk.sample_rate
                parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1))
                parts.append(np.zeros(int(rate * SENTENCE_PAUSE), dtype=np.float32))
            self._cache[key] = (np.concatenate(parts) if parts else np.zeros(1, np.float32), int(rate * factor))
        return self._cache[key]

    def say(self, text: str, slow: bool = True, stop_when=None, voice: str = "") -> bool:
        if not self.can_speak or not text.strip():
            return False
        speed = float(self.settings["word_speed"] if slow else self.settings["text_speed"])
        try:
            audio = self.synthesize(text, speed, voice)
        except Exception as exc:  # never stop a lesson because speech failed: carry on without it
            self._speech_failed(exc)
            return False
        self.play(*audio, stop_when=stop_when)
        return True

    def _speech_failed(self, exc: Exception) -> None:
        self.voice = self.sysvoice = None
        self.problems.append(BLOCKED_VOICE if blocked(exc) else
                             f"The voice stopped working ({exc}), so the app carries on without sound.")

    def say_lines(self, lines: list[tuple[str, str]], stop_when=None) -> bool:
        """A conversation: (voice, text) turns, each speaker in their own voice, played as one recording."""
        if not self.can_speak or not lines:
            return False
        speed, base = float(self.settings["text_speed"]), 22050
        parts = []
        try:
            for voice, text in lines:
                if text.strip():
                    audio, rate = self.synthesize(text, speed, voice)
                    parts += [_resample(audio, rate, base), np.zeros(int(base * TURN_PAUSE), dtype=np.float32)]
        except Exception as exc:
            self._speech_failed(exc)
            return False
        if parts:
            self.play(np.concatenate(parts), base, stop_when=stop_when)
        return True

    def _wait(self, stop_when=None) -> bool:
        """Wait for playback/recording to end. Polls, so Ctrl+C works on Windows too.
        Returns True if stop_when() asked to stop early."""
        stream = self.sd.get_stream()
        try:
            while stream.active:
                if stop_when and stop_when():
                    self.sd.stop()
                    return True
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.sd.stop()
            raise
        return False

    def play(self, audio: np.ndarray, rate: int, stop_when=None) -> bool:
        sd, device = self.sd, self.settings.get("output_device")
        if sd is None:
            return False
        try:
            try:
                sd.play(audio, rate, device=device)
            except sd.PortAudioError:
                # Some devices only accept their native sample rate.
                native = int(sd.query_devices(device, kind="output")["default_samplerate"])
                sd.play(_resample(audio, rate, native), native, device=device)
            return self._wait(stop_when)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # headphones unplugged, device gone, driver error: carry on without sound
            self.sd = None
            self.problems.append(f"The speakers stopped working ({exc}), so the app carries on without sound. "
                                 "Restart the app to try again.")
            return False

    def _input_rate(self) -> int:
        return int(self.sd.query_devices(self.settings.get("input_device"), kind="input")["default_samplerate"])

    def _mic_failed(self, exc: Exception) -> tuple[np.ndarray, int]:
        self.has_mic = False
        self.problems.append(f"The microphone stopped working ({exc}), so you'll say things out loud without "
                             "recording. Restart the app to try again.")
        return np.zeros(0, dtype=np.float32), 16000

    def record_seconds(self, seconds: float, on_tick=None) -> tuple[np.ndarray, int]:
        """Record for a fixed time; on_tick(seconds_left) is called about 10 times a second. A microphone that
        fails gives an empty recording (and is switched off), never an error."""
        try:
            rate = self._input_rate()
            rec = self.sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="float32",
                              device=self.settings.get("input_device"))
            start = time.monotonic()
            self._wait(lambda: bool(on_tick and on_tick(max(0.0, seconds - (time.monotonic() - start)))))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            return self._mic_failed(exc)
        self.last_peak = float(np.max(np.abs(rec))) if rec.size else 0.0
        return _tidy(rec[:, 0], rate), rate

    def record_until(self, wait_for_stop, max_seconds: int = 180) -> tuple[np.ndarray, int]:
        """Record until wait_for_stop() returns (e.g. the user presses Enter)."""
        rate = self._input_rate()
        frames: list[np.ndarray] = []

        def callback(indata, frame_count, time_info, status):
            frames.append(indata[:, 0].copy())

        try:
            with self.sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                     device=self.settings.get("input_device"), callback=callback):
                wait_for_stop()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            if type(exc).__name__ == "QuitSession":
                raise
            return self._mic_failed(exc)
        audio = np.concatenate(frames)[: max_seconds * rate] if frames else np.zeros(0, dtype=np.float32)
        self.last_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return _tidy(audio, rate), rate
