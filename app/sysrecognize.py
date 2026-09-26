"""Windows' own speech recognition, as the speech check when the offline one (Vosk) can't run: Smart App Control
or a school policy blocks its unsigned file. Windows' recognizer is part of Windows, so it's always allowed.

One PowerShell process stays open; each recording goes to it as a WAV file and comes back as text. It needs
Windows' German speech recognition, which comes with the German speech pack
(Settings → Time & language → Speech; or Language → Deutsch → Language options → Speech).
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$lang = $env:GTUTOR_RECOGNIZE_LANG
try {
  Add-Type -AssemblyName System.Speech
  $info = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() | Where-Object { $_.Culture.Name -like "$lang*" } | Select-Object -First 1
  if (-not $info) { [Console]::Out.WriteLine('NOREC'); [Console]::Out.Flush(); exit }
  $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
  $engine.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
  [Console]::Out.WriteLine('READY ' + $info.Culture.Name); [Console]::Out.Flush()
  while ($null -ne ($line = [Console]::In.ReadLine())) {
    try {
      $engine.SetInputToWaveFile($line)
      $words = @()
      while ($true) {
        try { $result = $engine.Recognize() } catch { break }  # "no audio input" at the end of the recording
        if ($null -eq $result) { break }
        $words += $result.Text
      }
      [Console]::Out.WriteLine('OK ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($words -join ' '))))
    } catch { [Console]::Out.WriteLine('ERR ' + $_.Exception.Message) }
    finally { try { $engine.SetInputToNull() } catch {} }
    [Console]::Out.Flush()
  }
} catch { [Console]::Out.WriteLine('ERR ' + $_.Exception.Message); [Console]::Out.Flush() }
"""
RATE = 16000


class WindowsRecognizer:
    """transcribe(audio, rate) -> what was heard, lower case ('' for nothing). Same shape as listen.Listener."""

    def __init__(self, language: str = "de") -> None:
        if os.name != "nt":
            raise RuntimeError("Windows speech recognition only exists on Windows")
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            env={**os.environ, "GTUTOR_RECOGNIZE_LANG": language}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._proc.stdin.write(SCRIPT.replace("\n", "\r\n") + "\r\n")
        self._proc.stdin.flush()
        first = self._proc.stdout.readline().strip()
        if not first.startswith("READY"):
            self.close()
            raise RuntimeError("no German Windows speech recognition is installed" if first == "NOREC"
                               else first or "no answer")
        self._dir = Path(tempfile.mkdtemp(prefix="gtutor-listen-"))
        self._n = 0

    def transcribe(self, audio: np.ndarray, rate: int) -> str:
        from .audio import _resample
        self._n += 1
        path = self._dir / f"{self._n}.wav"
        pcm = (np.clip(_resample(audio, rate, RATE), -1, 1) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        try:
            self._proc.stdin.write(f"{path}\n")
            self._proc.stdin.flush()
            answer = self._proc.stdout.readline().strip()
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # still in use for a moment: the temp folder is cleaned up by Windows
        self.last_answer = answer
        if not answer.startswith("OK"):
            return ""
        return base64.b64decode(answer[3:]).decode("utf-8").lower().strip() if len(answer) > 3 else ""

    def close(self) -> None:
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except Exception:
            self._proc.kill()
        finally:
            self._proc.stdout.close()
