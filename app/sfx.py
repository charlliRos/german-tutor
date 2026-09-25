"""Short retro game sounds (16-bit console style), made on the fly: right, almost, wrong, and "not now".

Each note is a band-limited pulse wave (only harmonics the ear can use, so it sounds crisp, not
harsh) with a 2 ms attack and a quick decay. config.json "sound_effects": false switches them off.
"""
from __future__ import annotations

import os

import numpy as np

# (frequency Hz, seconds, pulse width) per note
TUNES = {
    "right": [(987.77, 0.075, 0.25), (1318.51, 0.32, 0.25)],   # B5 -> E6, the classic coin "ding-ding"
    "almost": [(880.00, 0.07, 0.5), (880.00, 0.16, 0.5)],      # A5 twice: "nearly"
    "wrong": [(196.00, 0.11, 0.5), (138.59, 0.30, 0.5)],       # G3 -> C#3, a falling tritone "bonk-bonk"
    "buzz": [(110.00, 0.09, 0.5)],                             # A2 blip: "not so fast"
    "go": [(1046.50, 0.14, 0.25)],                             # C6 beep: "recording now, speak!"
}
VOLUME = {"right": 0.30, "almost": 0.22, "wrong": 0.28, "buzz": 0.22, "go": 0.25}
HARMONICS_UP_TO = 12000.0  # Hz
_clips: dict[tuple[str, int], np.ndarray] = {}


def _note(freq: float, seconds: float, width: float, rate: int) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    wave = np.zeros_like(t)
    for k in range(1, int(min(HARMONICS_UP_TO, rate / 2 - 500) / freq) + 1):
        wave += np.sin(np.pi * k * width) / k * np.cos(2 * np.pi * k * freq * t)
    wave /= np.max(np.abs(wave))
    envelope = np.minimum(t / 0.002, 1.0) * np.exp(-t * 3.0 / seconds)
    envelope[-int(rate * 0.004):] *= np.linspace(1.0, 0.0, int(rate * 0.004))  # no click at the end
    return wave * envelope


def render(name: str, rate: int) -> np.ndarray:
    if (name, rate) not in _clips:
        notes = [_note(f, s, w, rate) for f, s, w in TUNES[name]]
        _clips[name, rate] = (np.concatenate(notes) * VOLUME[name]).astype(np.float32)
    return _clips[name, rate]


def _enabled(audio) -> bool:
    return bool(getattr(audio, "settings", {}).get("sound_effects", True))


def play(audio, name: str, wait: bool = True) -> None:
    """Play a sound effect. wait=False returns at once (used while waiting for keys)."""
    if not _enabled(audio):
        return
    sd = getattr(audio, "sd", None)
    if sd is None:
        if name == "buzz":
            _system_beep()
        return
    device = audio.settings.get("output_device")
    try:
        rate = int(sd.query_devices(device, kind="output")["default_samplerate"])
        sd.play(render(name, rate), rate, device=device)
        if wait:
            audio._wait()
    except KeyboardInterrupt:
        sd.stop()
    except Exception:
        pass


def _system_beep() -> None:
    try:
        if os.name == "nt":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass
