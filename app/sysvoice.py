"""The computer's own voice, for when the Piper voice can't run: Windows' Smart App Control or a school policy
blocks its unsigned speech file, or Piper has no build for this computer. The system's speech engine is part
of the system, so it's always allowed.

- Windows: one PowerShell process stays open and turns each text into a WAV file with a German Windows voice
  (the speech-pack voices Katja, Hedda, Stefan). The voice comes with Windows' German speech pack
  (Settings → Time & language → Speech → Add voices → Deutsch).
- macOS: `say` with a German voice (Anna, Helena, Markus …; System Settings → Accessibility → Spoken Content).
- Linux: `espeak-ng` (or `espeak`) with its German voice (sudo apt install espeak-ng).
No extra download for the app itself.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$lang = $env:GTUTOR_VOICE_LANG
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
      $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
      $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $null = $t.Wait(-1); $t.Result }
  [void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
  [void][Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
  $voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -like "$lang*" } | Select-Object -First 1
  if (-not $voice) { [Console]::Out.WriteLine('NOVOICE'); [Console]::Out.Flush(); exit }
  $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
  $synth.Voice = $voice
  [Console]::Out.WriteLine('READY ' + $voice.DisplayName); [Console]::Out.Flush()
  while ($null -ne ($line = [Console]::In.ReadLine())) {
    try {
      $p = $line.Split("`t")
      $synth.Options.SpeakingRate = [double]::Parse($p[0], [Globalization.CultureInfo]::InvariantCulture)
      $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p[2]))
      $stream = Await ($synth.SynthesizeTextToStreamAsync($text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
      $size = [uint32]$stream.Size
      $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
      $null = Await ($reader.LoadAsync($size)) ([uint32])
      $bytes = New-Object byte[] $size
      $reader.ReadBytes($bytes)
      [IO.File]::WriteAllBytes($p[1], $bytes)
      [Console]::Out.WriteLine('OK')
    } catch { [Console]::Out.WriteLine('ERR ' + $_.Exception.Message) }
    [Console]::Out.Flush()
  }
} catch { [Console]::Out.WriteLine('ERR ' + $_.Exception.Message); [Console]::Out.Flush() }
"""


class WindowsVoice:
    """speak(text, speed) -> (float32 samples, sample rate). Raises RuntimeError if it can't."""

    def __init__(self, language: str = "de") -> None:
        if os.name != "nt":
            raise RuntimeError("the Windows voice only exists on Windows")
        env = {**os.environ, "GTUTOR_VOICE_LANG": language}
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # The script goes in on stdin; a line of its own ends it. After that, each line is one text to speak.
        self._proc.stdin.write(SCRIPT.replace("\n", "\r\n") + "\r\n")
        self._proc.stdin.flush()
        first = self._proc.stdout.readline().strip()
        if not first.startswith("READY"):
            self.close()
            raise RuntimeError("no German Windows voice is installed" if first == "NOVOICE" else first or "no answer")
        self.name = first[6:]
        self._dir = Path(tempfile.mkdtemp(prefix="gtutor-voice-"))
        self._n = 0

    def speak(self, text: str, speed: float) -> tuple[np.ndarray, int]:
        """speed: 1.0 normal, above 1 faster (Windows' SpeakingRate)."""
        self._n += 1
        path = self._dir / f"{self._n}.wav"
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._proc.stdin.write(f"{speed:.3f}\t{path}\t{b64}\n")
        self._proc.stdin.flush()
        answer = self._proc.stdout.readline().strip()
        if answer != "OK":
            raise RuntimeError(answer or "the Windows voice stopped")
        try:
            return read_wav(path)
        finally:
            path.unlink(missing_ok=True)

    def close(self) -> None:
        """End the PowerShell process (it also ends by itself when the app's input to it closes)."""
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except Exception:
            self._proc.kill()
        finally:
            self._proc.stdout.close()


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Mono float32 samples and the sample rate of a PCM WAV file."""
    with wave.open(str(path), "rb") as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    samples = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    samples = (samples - 128) / 128 if width == 1 else samples / float(2 ** (8 * width - 1))
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


class _CommandVoice:
    """A voice that is one command per text, writing a WAV file (macOS say, Linux espeak-ng)."""

    name = ""

    def __init__(self) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="gtutor-voice-"))
        self._n = 0

    def command(self, text: str, speed: float, path: Path) -> list[str]:
        raise NotImplementedError

    def speak(self, text: str, speed: float) -> tuple[np.ndarray, int]:
        self._n += 1
        path = self._dir / f"{self._n}.wav"
        done = subprocess.run(self.command(text, speed, path), capture_output=True, timeout=60)
        if done.returncode != 0 or not path.exists():
            raise RuntimeError(done.stderr.decode(errors="replace").strip() or "the system voice failed")
        try:
            return read_wav(path)
        finally:
            path.unlink(missing_ok=True)

    def close(self) -> None:
        pass


class MacVoice(_CommandVoice):
    def __init__(self, language: str = "de") -> None:
        if sys.platform != "darwin" or not shutil.which("say"):
            raise RuntimeError("macOS 'say' isn't available")
        voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=20).stdout.splitlines()
        german = [line.split()[0] for line in voices if f" {language}_" in line or f" {language}-" in line]
        if not german:
            raise RuntimeError("no German voice is installed (System Settings → Accessibility → Spoken Content)")
        super().__init__()
        self.name = german[0]

    def command(self, text: str, speed: float, path: Path) -> list[str]:
        return ["say", "-v", self.name, "-r", str(int(175 * speed)), "--data-format=LEI16@22050", "-o", str(path), text]


class EspeakVoice(_CommandVoice):
    def __init__(self, language: str = "de") -> None:
        self._exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not self._exe:
            raise RuntimeError("espeak-ng isn't installed (sudo apt install espeak-ng)")
        super().__init__()
        self.language, self.name = language, f"{Path(self._exe).name} ({language})"

    def command(self, text: str, speed: float, path: Path) -> list[str]:
        return [self._exe, "-v", self.language, "-s", str(int(150 * speed)), "-w", str(path), text]


def open_voice(language: str = "de"):
    """The best system voice for this computer. Raises RuntimeError saying what to install if there's none."""
    if os.name == "nt":
        return WindowsVoice(language)
    if sys.platform == "darwin":
        return MacVoice(language)
    return EspeakVoice(language)


def install_hint() -> str:
    if os.name == "nt":
        return "add Windows' German voice: Settings → Time & language → Speech → Add voices → Deutsch"
    if sys.platform == "darwin":
        return "add a German voice: System Settings → Accessibility → Spoken Content → System voice → Manage voices"
    return "install espeak-ng (e.g. sudo apt install espeak-ng)"
