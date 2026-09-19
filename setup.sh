#!/usr/bin/env sh
# One-time setup on Linux: virtual environment, libraries, German voice, "gtutor" command.
# Needs PortAudio for sound, e.g. Debian/Ubuntu: sudo apt install python3-venv libportaudio2
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/download_voice.py
.venv/bin/python tools/download_speech_model.py

# "gtutor" command in ~/.local/bin (on PATH by default on most distributions).
mkdir -p "$HOME/.local/bin"
printf '#!/usr/bin/env sh\nexec "%s/run.sh" "$@"\n' "$(pwd)" > "$HOME/.local/bin/gtutor"
chmod +x "$HOME/.local/bin/gtutor"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.profile"
       echo "Added ~/.local/bin to PATH in ~/.profile (log out and in again)." ;;
esac

echo
echo "Setup finished. Open a new terminal and type: gtutor"
