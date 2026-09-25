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
SILENCE_PEAK = 0.02    # recordings quieter than this count as "nothing heard"
QUIET_PEAK = 0.08      # below this the mic works but is set very low


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
        model = VOICES_DIR / f"{self.settings['voice']}.onnx"
        if not model.exists():
            self.problems.append("The German voice isn't downloaded yet. Run setup again (setup.bat or ./setup.sh).")
            return
        try:
            from piper import PiperVoice
            from piper.config import SynthesisConfig
        except Exception as exc:
            self.problems.append(f"Piper TTS is not installed ({exc}). Run the setup script again.")
            return
        try:
            self.voice = PiperVoice.load(model)
            self._synthesis_config = SynthesisConfig
        except Exception as exc:
            self.problems.append(f"Could not load the German voice ({exc}).")

    @property
    def can_speak(self) -> bool:
        return self.sd is not None and self.voice is not None

    @property
    def can_record(self) -> bool:
        return self.sd is not None and self.has_mic

    def synthesize(self, text: str, length_scale: float) -> tuple[np.ndarray, int]:
        key = (text, length_scale)
        if key not in self._cache:
            parts, rate = [], 22050
            config = self._synthesis_config(length_scale=length_scale)
            for chunk in self.voice.synthesize(clean_for_speech(text), config):
                rate = chunk.sample_rate
                parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1))
                parts.append(np.zeros(int(rate * SENTENCE_PAUSE), dtype=np.float32))
            self._cache[key] = (np.concatenate(parts) if parts else np.zeros(1, np.float32), rate)
        return self._cache[key]

    def say(self, text: str, slow: bool = True, stop_when=None) -> bool:
        if not self.can_speak or not text.strip():
            return False
        speed = float(self.settings["word_speed"] if slow else self.settings["text_speed"])
        self.play(*self.synthesize(text, speed), stop_when=stop_when)
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
        try:
            sd.play(audio, rate, device=device)
        except sd.PortAudioError:
            # Some devices only accept their native sample rate.
            native = int(sd.query_devices(device, kind="output")["default_samplerate"])
            sd.play(_resample(audio, rate, native), native, device=device)
        return self._wait(stop_when)

    def _input_rate(self) -> int:
        return int(self.sd.query_devices(self.settings.get("input_device"), kind="input")["default_samplerate"])

    def record_seconds(self, seconds: float, on_tick=None) -> tuple[np.ndarray, int]:
        """Record for a fixed time; on_tick(seconds_left) is called about 10 times a second."""
        rate = self._input_rate()
        rec = self.sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="float32",
                          device=self.settings.get("input_device"))
        start = time.monotonic()
        self._wait(lambda: bool(on_tick and on_tick(max(0.0, seconds - (time.monotonic() - start)))))
        self.last_peak = float(np.max(np.abs(rec))) if rec.size else 0.0
        return _tidy(rec[:, 0], rate), rate

    def record_until(self, wait_for_stop, max_seconds: int = 180) -> tuple[np.ndarray, int]:
        """Record until wait_for_stop() returns (e.g. the user presses Enter)."""
        rate = self._input_rate()
        frames: list[np.ndarray] = []

        def callback(indata, frame_count, time_info, status):
            frames.append(indata[:, 0].copy())

        with self.sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                 device=self.settings.get("input_device"), callback=callback):
            wait_for_stop()
        audio = np.concatenate(frames)[: max_seconds * rate] if frames else np.zeros(0, dtype=np.float32)
        self.last_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return _tidy(audio, rate), rate
