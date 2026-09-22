# nexon

Voice-controlled desktop assistant, split into modules.

## Install

```
pip install -r requirements.txt
pip install faster-whisper   # optional, recommended: local speech recognition
```

On Windows, if PyAudio gives trouble: `pip install pipwin && pipwin install pyaudio`.

OCR (read_screen / click / skip ad) needs the Tesseract-OCR engine
itself (not just the pytesseract wrapper) - install it from
https://github.com/UB-Mannheim/tesseract/wiki and either add it to
PATH or set `TESSERACT_CMD` in `nexon/config.py`.

## Run

```
python run_nexon.py
```

## Layout

```
run_nexon.py              entry point
nexon/
    config.py              every tunable setting (site shortcuts, thresholds, folders...)
    helpers.py              small generic utilities (extract_number, speak_long_text...)
    tts.py                  text-to-speech (single dedicated thread)
    speech.py               microphone + whisper/Google recognition
    ocr.py                  screenshot -> OCR -> "click this text" helpers
    pdf_reader.py           PDF filename search/index, open, page navigation
    registry.py             the @command decorator + dispatcher plumbing
    dispatcher.py           process_command() - the single entry point
    main.py                 wake-word state machine, kill switch, run loop
    commands/
        __init__.py         import order (see note below)
        timer.py             countdown timer + stopwatch
        volume.py
        brightness.py
        screen_reading.py    whatsapp / pdf / OCR screen reading / page nav
        scrolling.py
        click.py
        files.py             delete file, empty recycle bin
        dictation.py         type / dictate / send message
        browser.py           search, YouTube, open <site>, close tab(s)
        media.py             next/previous video, skip ad, play/pause
        system.py            screenshot
        exit_.py             shutdown/exit/quit/goodbye
```

## How commands work

Every phrase nexon understands is registered with a small decorator,
right next to the code that handles it:

```python
# nexon/commands/browser.py
from ..registry import command
from ..tts import speak

@command("open ")               # or a list of phrases, or a predicate function
def handle_open_website(command_text):
    ...
```

`nexon/dispatcher.py` doesn't know any phrases at all - it just imports
`nexon.commands` (which, as a side effect of being imported, runs every
`@command` decorator in every file listed in
`nexon/commands/__init__.py`) and then tries each registered handler,
in that import order, until one matches.

### Adding a command to an existing feature

Say you want a new browser command, e.g. "nexon reload page":

1. Open `nexon/commands/browser.py`.
2. Write the action (or reuse `pyautogui`/`webbrowser` directly) and a
   handler:

   ```python
   @command("reload page")
   def handle_reload_page(command_text):
       pyautogui.hotkey("ctrl", "r")
       speak("Reloading.")
   ```

3. Save. That's it - nothing in `dispatcher.py`, `main.py`, or any other
   file needs to change. The next run of nexon understands the phrase.

### Adding a whole new feature

1. Create `nexon/commands/your_feature.py` using any existing file as a
   template (import `command` from `..registry`, `speak` from `..tts`,
   write your functions, decorate the ones that should be commands).
2. Add one line to `nexon/commands/__init__.py`:
   `from . import your_feature`.

### A note on ordering

`@command` matches are tried in the order the *files* are imported in
`nexon/commands/__init__.py`, and within a file, in the order the
functions are defined. This only matters when one command's trigger
phrase could also match a broader command elsewhere - e.g. `"open pdf
..."` needs to be caught by `screen_reading.py` before `browser.py`'s
generic `"open <site>"` ever sees it. Those two spots are called out
with a comment in both `commands/__init__.py` and the files themselves.
For a brand-new, distinctly-worded command, import order essentially
never matters.

`match` for `@command(...)` can be:
- a string - matched as a substring (`"mute" in command_text`)
- a list of strings - matches if ANY is a substring
- a function - `predicate(command_text) -> bool`, for `startswith`,
  regex, or combined conditions

A handler returns `True` (or nothing) to keep nexon running, or `False`
to shut it down (used only by the exit command).

## Notes carried over from the original single-file version

- All speech output is routed through one dedicated thread (`nexon/tts.py`)
  because pyttsx3's engine isn't safe to call from multiple threads at once.
- "read screen" is PDF-aware: if the focused window looks like a PDF
  viewer, it reads the real text via PyMuPDF instead of OCR-ing pixels,
  and remembers your page for "next page"/"previous page"/"read page N".
- "next page"/"previous page"/"go to page X" work even without a PDF
  loaded into nexon's own reader, by falling back to Page Up/Down/Ctrl+G
  keystrokes sent to whichever window is focused.
- "search <query>" opens Google in a tab AND fetches the same page to
  read the first organic result aloud (best-effort - Google's HTML
  changes periodically and can occasionally show a CAPTCHA instead).
- "close tab"/"close all tabs" and "delete file" are plain keystrokes
  sent to whichever window has focus - make sure the right app/item is
  focused before using them.
- Exact volume/brightness percentages (pycaw) are Windows-only. For
  cross-platform volume, swap `nexon/commands/volume.py`'s `set_volume()`
  for an `osascript` (macOS) or `pactl`/`amixer` (Linux) call.

## What changed structurally vs. the original single file

- `commands/system.py`'s screenshot now actually increments the saved
  filename (`Screenshot1.png`, `Screenshot2.png`, ...) - in the
  original, the save path was built once at import time from the
  starting counter value, so every screenshot silently overwrote
  `Screenshot1.png`. Everything else is a straight move into modules,
  not a behavior change.
