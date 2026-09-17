#!/usr/bin/env sh
# One-time setup on Linux: virtual environment, libraries, German voice.
# Needs PortAudio for sound, e.g. Debian/Ubuntu: sudo apt install python3-venv libportaudio2
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/download_voice.py
echo
echo "Setup finished. Start the tutor with: ./run.sh"
