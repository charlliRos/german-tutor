# Deutsch mit Fritz & Pip

An offline German tutor for the terminal (Windows + Linux), made for teenagers.
Fritz the Dackel and Pip the robin say hello when it starts.

**Every day:**
1. **Warm-up (scored).** Vocabulary from everyday German and STEM: English→German or German→English, with the German read out loud. Sometimes you say the word into the microphone and hear your recording next to the correct pronunciation. Words you know come back less often (spaced repetition).
2. **Reading (not scored).** One paragraph from a German classic, read aloud and explained in English. Then one random task: read it into the mic, translate it to English, or translate it back to German. Your answer is shown next to the reference so you can grade yourself.

No internet, no AI at runtime. Speech is generated offline with [Piper](https://github.com/OHF-Voice/piper1-gpl).

## Setup

| | Windows | Linux |
|---|---|---|
| Needs | Python 3.10+ | Python 3.10+, `sudo apt install python3-venv libportaudio2` |
| Install (once) | `setup.bat` | `./setup.sh` |
| Start | `run.bat` | `./run.sh` |

Options: `--profile NAME` (skip the chooser), `--no-audio`.
Each kid gets their own profile. Progress is saved in `data/profiles/`, and their typed translations in `data/profiles/<name>_journal.jsonl`.

Settings (words per day, STEM share, speech speed, mic device…) are in `config.json`.
To list audio devices: `.venv\Scripts\python -m sounddevice`.

## Adding content (for the parent)

- The format is described in [CONTENT_FORMAT.md](CONTENT_FORMAT.md).
- Vocabulary: `content/vocab/*.json`. Books: `content/books/*.json`.
- New book: `python tools/split_text.py text.txt content/books/11_author_title.json --title ... --author ...` creates the units. Then fill in `en`, `explain_en` and `words`.
- Always run `python tools/validate_content.py` afterwards.
- Tests: `python -m unittest discover -s tests -t .`

Texts are public domain (the author died more than 70 years ago). Spelling is modernised, wording unchanged. Translations were written for this app.
