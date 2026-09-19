# Deutsch mit Fritz & Pip

An offline German tutor for the terminal (Windows + Linux), made for teenagers.
Fritz the Dackel and Pip the robin say hello when it starts.

**Every day:**
1. **Warm-up (scored).** About 1,900 words from everyday German, STEM and "official German" (offices, forms, taxes, permits): English→German or German→English, with the German read out loud. Sometimes you say the word into the microphone and hear your recording next to the correct pronunciation. The warm-up **starts with 10 words and grows about half a word per practice day, to 200 words after a year**. It mixes new words, words that are due (spaced repetition) and extra practice on weaker words. Missed words come back at the end, again and again, until you get them right. Run it again any time for extra practice.
2. **Reading (not scored), built on repetition.** The next paragraph of a German classic, read aloud, in 3 rounds: translate it to English, see what it means (explained in English, with key words), read it into the mic, then translate it back to German. Your answer is shown next to the reference so you can grade yourself. After the new paragraph comes a **look back**: every paragraph returns in each of the next 2 sessions (session 3 repeats sessions 1 and 2) and again 1, 3, 7, 16 and 35 days after you learned it, each time with a different exercise. "Needs work" means it comes back next session. The paragraph's key words also come back in the next warm-up, new ones and ones you already know. Long books go from key scene to key scene, with short English "Meanwhile in the story…" recaps, all the way to the ending. To start a book again, use "Choose a book".

No AI at runtime. After setup it needs no internet. Speech is generated offline with [Piper](https://github.com/OHF-Voice/piper1-gpl).

## Install

Needs internet once (setup downloads the libraries and the German voice, ~63 MB).

### Windows

1. **Install Python and Git** (skip what you already have). In PowerShell:
   ```
   winget install Python.Python.3.12
   winget install Git.Git
   ```
   Or download Python from [python.org](https://www.python.org/downloads/) (tick **"Add python.exe to PATH"**) and Git from [git-scm.com](https://git-scm.com/downloads).
2. **Get the app.** Open a **new** PowerShell window and run:
   ```
   git clone https://github.com/charlliRos/german-tutor.git
   ```
   This creates a `german-tutor` folder. (Without Git you can click **Code → Download ZIP** on GitHub and unzip it, but then `gtutor update` won't work.)
3. **Run setup.** Double-click **`setup.bat`** in the app folder. It takes a few minutes and also adds the `gtutor` command.
4. **Start.** Open a **new** terminal and type:
   ```
   gtutor
   ```
   Or double-click `run.bat`. Type your name: a short welcome explains how it works and offers to test your speakers and microphone (also in the menu as **7**).

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
gtutor update            # get the latest words, books and fixes
gtutor report            # every kid's progress on one screen (for parents)
```

## Progress

Each kid has a profile. Progress is saved automatically after every word and every paragraph, so quitting is safe: type `q` (or press Ctrl+C) to leave an activity, and `q` on the menu to close the app:
- `data/profiles/<name>.json`: word boxes, reading position, daily history
- `data/profiles/<name>_journal.jsonl`: every translation they typed, with their self-grade

### Checking progress (for the parent)

```
gtutor report                 # all kids
gtutor report --profile Anna  # one kid
```

It starts with a one-line overview per kid. Then, for each kid: when they last practised, practice days and time in the last 7 and 30 days, a 4-week calendar, words learned, reading position, the 10 words they still miss most, and their last 5 translations next to the reference (with the grade they gave themselves). Practice time counts the time between answers; one long pause counts as at most 5 minutes. The report only reads the profiles.

`data/` is not uploaded to GitHub. To move a kid to another computer, copy `data/profiles/` across.

## Updating

To get the latest app, words and books, type:
```
gtutor update
```
It downloads the changes from GitHub and installs new libraries if needed. It never touches progress, and your own `config.json` edits are kept.

If you installed from a ZIP (no git), download the new ZIP instead, unzip it over the old folder, and keep your `data/` folder.

## Settings

Edit `config.json`: warm-up size (`warmup_start`, `warmup_max`, `warmup_growth`, `new_word_share`), the mix of everyday / STEM / official words (`bank_shares`), paragraphs per day, look backs per session (`paragraph_reviews_per_session`), key words from reading per day (`reading_words_per_day`), how often to speak, speech speed, sound effects on/off (`sound_effects`), microphone/speaker device. To list audio devices: `.venv\Scripts\python -m sounddevice`.

## Adding content (for the parent)

- The format is described in [CONTENT_FORMAT.md](CONTENT_FORMAT.md). Vocabulary goes in `content/vocab/*.json`, books in `content/books/*.json`.
- New book: `python tools/split_text.py text.txt content/books/11_author_title.json --title ... --author ...` creates the units. Then fill in `en`, `explain_en` and `words`.
- Always run `python tools/validate_content.py` afterwards.
- Tests: `python -m unittest discover -s tests -t .`

Texts are public domain (the author died more than 70 years ago). Spelling is modernised, wording unchanged. Translations were written for this app.
