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

See **[commandlist.md](commandlist.md)** for every command and phrase
variation nexon understands.

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
        mail.py              check email / read latest email (IMAP)
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

Please keep `commandlist.md` updated too when you add or change a command.

## A note on ordering

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

## Email (free - standard library only, no API key)

`nexon/commands/mail.py` checks email over IMAP using only `imaplib` +
`email` from the Python standard library - no pip install, no paid API,
works with any IMAP provider.

**Commands:**
- "check email" / "check my mail" / "any new emails" - unread count and
  sender/subject for each, across every folder in `EMAIL_FOLDERS`
- "check email in `<folder>`" - just that one folder
- "read email" / "read latest email" - reads the newest unread email's
  full body aloud

**Setup (Gmail, free):**
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
   (your normal Google password does not work over IMAP)
3. Gmail Settings -> "Forwarding and POP/IMAP" -> Enable IMAP
4. Set two environment variables (don't paste real credentials into
   `config.py` - they'd end up committed to version control):
   ```
   setx NEXON_EMAIL_USER "you@gmail.com"
   setx NEXON_EMAIL_PASSWORD "your16charapppassword"
   ```
   (open a new terminal afterward so the variables take effect)

**Other providers:** same idea (an app password once 2FA is on), just a
different `IMAP_HOST` in `config.py` - `outlook.office365.com` for
Outlook/Hotmail, `imap.mail.yahoo.com` for Yahoo. Work/enterprise
accounts sometimes disable basic IMAP auth entirely in favor of OAuth
("modern auth") - if login fails with those, IMAP access may need to be
turned on by an admin, or may not be available at all.

**Folders:** `EMAIL_FOLDERS` in `config.py` is a list, so you can check
several: `["INBOX", "[Gmail]/Starred", "Work"]`. Gmail labels show up as
folders this way too.

## WhatsApp

`read_whatsapp()` (in `commands/screen_reading.py`) is OCR-based: it
screenshots the WhatsApp Desktop window and reads the pixels. That's
the practical free option for reading your own chats - the alternatives
aren't a clean upgrade:
- The official WhatsApp Business API has a free tier, but it's built
  for businesses messaging customers, not for reading your own personal
  chats.
- Scraping WhatsApp Web with Selenium gets real text instead of OCR
  guesses, but violates WhatsApp's Terms of Service for personal
  accounts, breaks whenever they change their web UI, and risks the
  account getting flagged.

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
