# Deutsch mit Fritz & Pip

An offline German tutor for the terminal (Windows + Linux), made for teenagers.
Fritz the Dackel and Pip the robin say hello when it starts.

**Every day:**
1. **Warm-up (scored).** About 1,900 words from everyday German, STEM and "official German" (offices, forms, taxes, permits): English→German or German→English, with the German read out loud. Sometimes you say the word into the microphone and hear your recording next to the correct pronunciation. Words you know come back less often (spaced repetition).
2. **Reading (not scored).** The next paragraph of a German classic, read aloud and explained in English. Then one random task: read it into the mic, translate it to English, or translate it back to German. Your answer is shown next to the reference so you can grade yourself. Long books go from key scene to key scene, with short English "Meanwhile in the story…" recaps, all the way to the ending.

No AI at runtime. After setup it needs no internet. Speech is generated offline with [Piper](https://github.com/OHF-Voice/piper1-gpl).

## Install

Needs internet once (setup downloads the libraries and the German voice, ~63 MB).

### Windows

1. **Install Python** (skip if you have it). In PowerShell:
   ```
   winget install Python.Python.3.12
   ```
   Or download it from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. **Get the app.** Either run `git clone https://github.com/charlliRos/german-tutor.git`, or on GitHub click **Code → Download ZIP** and unzip it.
3. **Run setup.** Double-click **`setup.bat`** in the app folder. It takes a few minutes and also adds the `gtutor` command.
4. **Start.** Open a **new** terminal and type:
   ```
   gtutor
   ```
   Or double-click `run.bat`. Type your name, then choose **7** to test your speakers and microphone.

### Linux (Debian/Ubuntu)

```
sudo apt install python3-venv libportaudio2 git
git clone https://github.com/charlliRos/german-tutor.git
cd german-tutor
./setup.sh
gtutor            # in a new terminal; or ./run.sh
```

### Options

```
gtutor --profile Anna    # skip the name chooser
gtutor --no-audio        # no speech or microphone
```

## Progress

Each kid has a profile. Progress is saved automatically after every word and every paragraph, so quitting is safe (type `:quit` or `:exit` to leave an activity, or press Ctrl+C):
- `data/profiles/<name>.json`: word boxes, reading position, daily history
- `data/profiles/<name>_journal.jsonl`: every translation they typed, with their self-grade

`data/` is not uploaded to GitHub. To move a kid to another computer, copy `data/profiles/` across.

## Updating

To get new books and words: in the app folder run `git pull` (or download the ZIP again and keep your old `data/` folder). Then run `setup.bat` / `./setup.sh` again if `requirements.txt` changed.

## Settings

Edit `config.json`: words per day, the mix of everyday / STEM / official words (`bank_shares`), paragraphs per day, how often to speak, speech speed, microphone/speaker device. To list audio devices: `.venv\Scripts\python -m sounddevice`.

## Adding content (for the parent)

- The format is described in [CONTENT_FORMAT.md](CONTENT_FORMAT.md). Vocabulary goes in `content/vocab/*.json`, books in `content/books/*.json`.
- New book: `python tools/split_text.py text.txt content/books/11_author_title.json --title ... --author ...` creates the units. Then fill in `en`, `explain_en` and `words`.
- Always run `python tools/validate_content.py` afterwards.
- Tests: `python -m unittest discover -s tests -t .`

Texts are public domain (the author died more than 70 years ago). Spelling is modernised, wording unchanged. Translations were written for this app.
