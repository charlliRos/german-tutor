#!/usr/bin/env sh
# One-time setup on Linux and macOS: virtual environment, libraries, German voice, "gtutor" command.
# Linux needs PortAudio for sound: Debian/Ubuntu: sudo apt install python3-venv libportaudio2
#   Fedora: sudo dnf install portaudio · Arch: sudo pacman -S portaudio · macOS: nothing extra.
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
# The voice and the speech checker can be downloaded later (gtutor update): the app works without them.
.venv/bin/python tools/download_voice.py || echo "Couldn't download the German voice now: run 'gtutor update' later."
.venv/bin/python tools/download_speech_model.py || echo "Couldn't download the speech checker now: run 'gtutor update' later."

# "gtutor" command in ~/.local/bin (on PATH by default on most distributions).
mkdir -p "$HOME/.local/bin"
printf '#!/usr/bin/env sh\nexec "%s/run.sh" "$@"\n' "$(pwd)" > "$HOME/.local/bin/gtutor"
chmod +x "$HOME/.local/bin/gtutor"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) # ~/.profile for most Linux shells; zsh (macOS) and bash with a ~/.bash_profile read their own file.
       for rc in "$HOME/.profile" "$HOME/.zprofile" "$HOME/.bash_profile"; do
           if [ "$rc" = "$HOME/.profile" ] || [ -f "$rc" ] || { [ "$rc" = "$HOME/.zprofile" ] && [ "$(uname)" = Darwin ]; }; then
               echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
               echo "Added ~/.local/bin to PATH in $rc."
           fi
       done
       echo "Open a new terminal (or log out and in again) for the gtutor command." ;;
esac

echo
echo "Setup finished. Open a new terminal and type: gtutor"
