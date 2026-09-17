"""
nexon - simple voice-controlled desktop assistant

Install:
    pip install SpeechRecognition pyttsx3 PyAudio pyautogui screen-brightness-control ^
                keyboard pycaw comtypes pytesseract pygetwindow pywhatkit pymupdf Pillow ^
                requests beautifulsoup4

If PyAudio gives you trouble on Windows:
    pip install pipwin
    pipwin install pyaudio

Extra one-time setup:
    - OCR (read_screen / read_whatsapp) needs the Tesseract-OCR engine itself,
      not just the pytesseract wrapper. On Windows, install it from:
          https://github.com/UB-Mannheim/tesseract/wiki
      and either add it to PATH, or set the path explicitly below via
      pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    - read_whatsapp() reads whatever is currently visible in the WhatsApp
      Desktop window using OCR (a screenshot of that window, not the
      WhatsApp API). WhatsApp Desktop must be open. It can only "see" text
      currently on screen — it can't scroll or open specific chats for you,
      and it can't tell a real new message from an old one except by noticing
      the visible text changed since last time you asked.

    - "play <song> on YouTube" uses pywhatkit.playonyt(), which looks up the
      top YouTube result and opens it directly in your browser (no need to
      click search/play yourself).

    - "read screen" now checks whether the active window looks like a PDF
      viewer. If so, it locates the actual file (by searching Desktop,
      Documents, and Downloads for a matching filename) and reads the real
      text straight from the PDF via PyMuPDF - far more accurate than OCR.
      It remembers which page you're on, so "next page" / "previous page" /
      "read page 5" work afterward. If a page has no extractable text (a
      scanned image page), it falls back to OCR on just that page. If no
      PDF is detected at all, "read screen" falls back to OCR-ing the whole
      screen like before. You can also say "read pdf <name>" to open a
      specific PDF by (partial) filename regardless of what's focused, and
      it loads into nexon so it can be read aloud / paged through.

    - "launch pdf <name>" (or "open pdf <name>") is different from "read
      pdf": it just opens the matching PDF in your normal default PDF
      viewer (via os.startfile), the same as double-clicking it. It doesn't
      load it into nexon's internal reader/page-tracking state. Windows only.

    - PDF filename matching is fuzzy: it normalizes punctuation/underscores
      to spaces and, if there's no exact word match, falls back to a
      similarity score. So "read pdf project proposal" can still find
      "Project_Proposal_Final_v2.pdf" even though the words don't line up
      exactly with what you said.

    - "close tab" (Ctrl+W) and "close all tabs" (Ctrl+Shift+W) are plain
      keystrokes sent to whichever window currently has focus - they work
      great in a browser, but if something else is focused when you say
      them, those keys will do whatever THAT app maps them to (often
      closing its current document/window instead). Make sure your
      browser is the focused window before using these. "close all tabs"
      is checked before "close tab" in process_command so the two phrases
      can't be confused with each other. Note Ctrl+Shift+W closes the
      whole browser window in most browsers - there's no universal
      keyboard shortcut for "close every tab but leave the window open".

    - All speech output (speak()) is routed through a single dedicated
      background thread (see _tts_worker below). pyttsx3's engine is not
      safe to call from more than one thread at once - e.g. skip_ad()'s
      background polling thread calling speak() to announce "Skipped the
      ad." at the same time the main loop's next command tries to speak
      could leave the engine (SAPI5 on Windows, COM-based) in a broken
      state, which used to look like nexon "freezing" right after a skip.
      Now every speak() call, from any thread, just enqueues text for the
      one worker thread that owns the engine.

    - "click <text>" / "double click <text>" OCRs the whole screen and
      clicks the center of whichever line of text best matches what you
      said (exact substring > all-words-present > fuzzy ratio, using the
      same PDF_FUZZY_MATCH_THRESHOLD as PDF filename matching). This only
      works on things with visible, OCR-readable text - a labeled button,
      a video title, a menu item. It can't click a bare icon or unlabeled
      thumbnail since there's no text there to match against.

    - "search <query>" opens a Google results tab AND fetches the same
      page directly to read the first organic result aloud. Google's
      result HTML changes periodically without notice, and rapid
      automated requests can occasionally trigger a CAPTCHA page instead
      of real results - if that happens the tab still opens fine, nexon
      just can't read a result aloud that time.

    - "type <text> and search" / "type <text> and enter" fills whatever
      field currently has focus - a search bar, address bar, any form
      field - and submits it. This is the generic counterpart to "send
      message": same underlying typing mechanism, just not framed as
      sending a chat message. Plain "type <text>" (no "and enter"/"and
      search" suffix) still just fills the field without submitting.

    - "delete file" (or "delete this file"/"delete the file") assumes
      something is already selected on screen - typically via a prior
      "click <filename>" - and just sends the Delete key, which moves
      the selected item to the Recycle Bin. Add "permanently" or
      "forever" to the phrase (e.g. "delete this file permanently") to
      send Shift+Delete instead, which skips the Recycle Bin - Windows
      may show a confirmation dialog for that, which nexon does not
      click through. Like the tab-closing commands, this is just a
      keystroke sent to whichever window has focus, so make sure File
      Explorer (with the right item selected) is focused first.

    - "clear recycle bin" / "empty recycle bin" empties the Windows
      Recycle Bin directly via shell32, with no confirmation dialog.
      Windows only.

Note: exact volume control (pycaw) is Windows-only. If you need
cross-platform support, swap set_volume() for an osascript (macOS)
or pactl/amixer (Linux) call.
"""

import time
import re
import os
import glob
import difflib
import queue
import threading
import webbrowser
import speech_recognition as sr
import pyttsx3
import pyautogui
import screen_brightness_control as sbc
import keyboard
import pytesseract
import pygetwindow as gw
import pywhatkit
import pymupdf
from PIL import Image

try:
    import winsound  # stdlib, Windows only - used to ring the countdown timer
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# If Tesseract isn't on PATH, uncomment and set this:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def kill_switch():
    print("nexon kill switch activated!")
    os._exit(0)


keyboard.add_hotkey("ctrl+alt+j", kill_switch)

# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

WAKE_WORD = "nexon"

# Phrases (heard AFTER the wake word) that toggle "awake" mode, where
# nexon stops requiring the wake word before every command and just tries
# to match anything it hears against a command instead.
STAY_AWAKE_PHRASES = ("awake", "keep listening", "always listen")

# Phrases that drop nexon back out of "awake" mode into the normal
# wake-word-required state. Checked WITHOUT needing "nexon" first while
# already in awake mode (that's the whole point), but also work the
# normal "nexon sleep" way since process_command never sees them directly.
SLEEP_PHRASES = ("sleep", "go to sleep", "stop listening")

# How long nexon waits for you to actually say the command after it
# replies "Yes?" (you said just the wake word with nothing after it)
COMMAND_TIMEOUT = 10

# Safety ceiling on how long a single phrase can run in the ALWAYS-ON
# background listener before it's cut and sent off for recognition
# regardless of whether you've paused. This is NOT how long nexon "waits
# to hear you" anymore - the mic is open continuously - it just stops a
# single phrase from running forever if you never pause. Normally a
# phrase ends on its own after PAUSE_THRESHOLD seconds of silence.
PHRASE_TIME_LIMIT = 30

# How long a pause (in seconds) ends a phrase and sends it off for
# recognition. SpeechRecognition's own default here is 0.8, which is
# tuned for short, snappy commands - on anything longer, a normal
# mid-sentence breath or thinking pause easily exceeds 0.8s, so the
# phrase gets cut there and everything after the pause is either lost or
# treated as a separate, wake-word-less utterance. 1.4 gives real pauses
# room without making nexon feel sluggish to respond.
PAUSE_THRESHOLD = 1.4

# No ceiling at all for dictation (see listen_raw()) - a message you're
# dictating should only end when you actually stop talking, not when it
# hits an arbitrary length.
DICTATION_PHRASE_TIME_LIMIT = None

VOLUME_STEP = 5
BRIGHTNESS_STEP = 10

# Mouse / scrolling controls
SCROLL_STEP = 5
CLICK_MOVE_DURATION = 0.08
DOUBLE_CLICK_INTERVAL = 0.15

# How many characters of OCR'd text to actually speak aloud (long screens
# would otherwise take forever to read out)
MAX_SPOKEN_CHARS = 500

# Minimum similarity (0-1) accepted for a fuzzy PDF filename match when no
# exact/word match is found. Lower = more forgiving, but more false hits.
PDF_FUZZY_MATCH_THRESHOLD = 0.55

# Common site shortcuts so "open youtube" works without saying ".com"
SITE_SHORTCUTS = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "whatsapp web": "https://web.whatsapp.com",
    "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com",
    "facebook": "https://facebook.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://reddit.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "ao3" : "https://archiveofourown.org/",
}

# Folders searched (recursively) when trying to locate a PDF by filename
PDF_SEARCH_DIRS = [
    os.path.expanduser("C:/Users/rabey/Desktop"),
    os.path.expanduser("C:/Users/rabey/Documents"),
    os.path.expanduser("C:/Users/rabey/Downloads"),
]


# --------------------------------------------------
# SETUP
# --------------------------------------------------

recognizer = sr.Recognizer()
recognizer.pause_threshold = PAUSE_THRESHOLD

# Remembers the last thing OCR'd from WhatsApp so we can tell what's new
_last_whatsapp_text = ""

# Tracks the currently "open" PDF for read screen / next page / previous page
_pdf_state = {"path": None, "doc": None, "page": 0}

# Stopwatch: None when not running, else time.time() it was started
_stopwatch_start = None

# Countdown timers currently running (threading.Timer objects), so they
# can all be cancelled with "cancel timer"
_active_timers = []

# When True, nexon skips the wake-word check and treats every heard phrase
# as a command directly. Toggled by "nexon awake" / "sleep".
_stay_awake = False


# --------------------------------------------------
# TEXT-TO-SPEECH (single dedicated thread)
# --------------------------------------------------
#
# pyttsx3 (and the SAPI5/COM engine it wraps on Windows) is not safe to
# use from multiple threads. Several call sites need to speak from a
# background thread - skip_ad()'s polling worker, countdown timers ringing
# via threading.Timer - and if one of those overlaps with the main loop
# calling speak() for the next command, the engine can end up wedged
# (a COM error, or pyttsx3's "run loop already started"), after which
# every subsequent speak() call can hang or silently do nothing. That's
# what looked like nexon "breaking down" right after a skip ad.
#
# The fix: create and use the pyttsx3 engine on exactly one thread, ever.
# Every other thread just drops text into a queue for that thread to speak.

_tts_queue = queue.Queue()

# True while nexon is actually speaking. The background listener (added
# below) checks this and drops whatever it just heard instead of treating
# it as a command - otherwise, with the mic always on, nexon's own voice
# coming out of the speakers can get picked back up and misheard as you
# talking to it.
_is_speaking = threading.Event()


def _tts_worker():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass  # not on Windows / pywin32 unavailable - fine for other drivers

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)
    engine.setProperty("volume", 1.0)

    while True:
        text = _tts_queue.get()
        try:
            if text is None:
                break
            print(f"nexon: {text}")
            _is_speaking.set()
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            # Small grace period: audio lingering in the air / speaker
            # buffers can still reach the mic for a moment after
            # runAndWait() returns.
            time.sleep(0.3)
            _is_speaking.clear()
            _tts_queue.task_done()


_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


def speak(text, wait=True):
    """
    Speak text aloud. Safe to call from any thread - this only ever
    enqueues the text; the actual pyttsx3 engine is owned and driven
    entirely by _tts_worker on its own thread.

    wait=True (the default) blocks until everything currently queued has
    been spoken, so call sites that depend on speak() finishing before
    doing the next thing (e.g. "Go ahead, I'm listening" right before we
    start recording) behave the same as before. Pass wait=False for a
    fire-and-forget announcement.
    """
    _tts_queue.put(text)
    if wait:
        _tts_queue.join()


# --------------------------------------------------
# SPEECH RECOGNITION
# --------------------------------------------------

# --------------------------------------------------
# ALWAYS-ON BACKGROUND LISTENING
# --------------------------------------------------
#
# The old approach called a blocking listen() in a loop: open the mic,
# wait up to PHRASE_TIME_LIMIT seconds of audio, close the mic, THEN send
# it off to Google for recognition, and only after all of that loop back
# around and open the mic again. Two things fell out of that:
#
#   1. PHRASE_TIME_LIMIT was a hard ceiling on the mic capture itself, so
#      any command that took longer to say than that limit got cut off
#      mid-sentence.
#   2. The mic was only ever open DURING that fixed window. Recognition
#      (a network round-trip to Google) happens after the mic closes, and
#      there's also the small overhead of tearing down and re-opening the
#      PyAudio stream every loop iteration. Anything you said during that
#      gap - including right after nexon finished a previous command -
#      was simply never captured.
#
# SpeechRecognition's listen_in_background() fixes both: it keeps exactly
# one mic stream open continuously on its own thread for as long as the
# program runs, and calls a callback for every phrase it detects (a
# phrase ends on its own after PAUSE_THRESHOLD seconds of silence, not a
# fixed clock). PHRASE_TIME_LIMIT is only a safety ceiling now, not the
# listening window, so it can be generous. Recognized text is dropped
# into a queue; the main loop just pulls from that queue instead of
# calling into the mic directly, so there's never a gap where nexon isn't
# listening.

_heard_queue = queue.Queue()


def _background_listen_callback(recognizer_instance, audio):
    """
    Runs on SpeechRecognition's background thread for every phrase it
    captures. Recognizes it and, if it's not empty and nexon isn't
    currently talking (see _is_speaking), drops the text on the queue
    for the main loop to pick up.
    """
    if _is_speaking.is_set():
        return

    try:
        text = recognizer_instance.recognize_google(audio).lower().strip()
    except sr.UnknownValueError:
        return
    except sr.RequestError as e:
        print(f"Speech recognition error: {e}")
        return

    if text and not _is_speaking.is_set():
        print(f"You: {text}")
        _heard_queue.put(text)


# Holds the stop_listening() callable SpeechRecognition gives back, so
# pause/resume can stop and restart the one background stream. Only ever
# one mic stream should be open at a time - PyAudio doesn't handle two
# overlapping opens on the same device well - so anything that needs the
# mic directly (like listen_raw() below) must pause this first.
_stop_listening = None


def start_background_listening():
    """
    Calibrates for ambient noise once, then starts the persistent
    background listener. Returns the stop_listening() callable that
    SpeechRecognition gives back, so main() can shut it down cleanly.
    """
    global _stop_listening

    mic = sr.Microphone()

    with mic as source:
        print("Calibrating microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    # Lock the energy threshold in place after that one calibration
    # instead of letting it keep auto-adjusting for the rest of the
    # session. With dynamic adjustment left on, a long-running
    # background listener can have its threshold drift upward (e.g. from
    # a fridge humming or a fan kicking in) until it starts reading part
    # of your actual speech as background noise and cutting phrases
    # early - which looks exactly like "it heard me but didn't get all
    # of it." A fixed threshold from a clean calibration is more
    # predictable for a listener that never stops running.
    recognizer.dynamic_energy_threshold = False

    _stop_listening = recognizer.listen_in_background(
        mic,
        _background_listen_callback,
        phrase_time_limit=PHRASE_TIME_LIMIT
    )
    return _stop_listening


def pause_background_listening():
    """
    Stops the always-on listener so a call site that needs the mic
    directly (e.g. listen_raw() for dictation) can open its own stream
    without fighting the background one for the same device. Always
    pair with resume_background_listening().
    """
    global _stop_listening
    if _stop_listening is not None:
        _stop_listening(wait_for_stop=True)
        _stop_listening = None


def resume_background_listening():
    """Restarts the always-on listener after pause_background_listening()."""
    if _stop_listening is None:
        start_background_listening()


def get_heard(timeout=None):
    """
    Pull the next recognized phrase off the background listener's queue.
    Returns "" if nothing came in within `timeout` seconds (or
    immediately, if timeout is None/0 and the queue is empty).
    """
    try:
        return _heard_queue.get(timeout=timeout)
    except queue.Empty:
        return ""


def listen_raw():
    """
    Blocking single-shot listen that preserves original casing/
    punctuation from the recognizer instead of lowercasing - used for
    dictating actual message text (see dictate_and_type). Pauses the
    always-on background listener for the duration of the call and
    resumes it afterward, since only one mic stream can be open at once.
    """
    pause_background_listening()
    try:
        with sr.Microphone() as source:
            print("Listening...")
            try:
                audio = recognizer.listen(
                    source,
                    timeout=COMMAND_TIMEOUT,
                    phrase_time_limit=DICTATION_PHRASE_TIME_LIMIT
                )
            except sr.WaitTimeoutError:
                return ""
    finally:
        resume_background_listening()

    try:
        text = recognizer.recognize_google(audio)
        print(f"You (dictated): {text}")
        return text.strip()

    except sr.UnknownValueError:
        return ""

    except sr.RequestError as e:
        print(f"Speech recognition error: {e}")
        return ""


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def extract_number(command):
    """Pull the first integer out of a spoken command, e.g. 'set volume to 50' -> 50."""
    match = re.search(r"\d+", command)
    return int(match.group()) if match else None


def speak_long_text(text, prefix=None):
    """Speak (and print) a block of OCR'd/long text, capped to a sane length."""
    text = text.strip()
    if not text:
        return False
    if prefix:
        speak(prefix)
    if len(text) > MAX_SPOKEN_CHARS:
        text = text[:MAX_SPOKEN_CHARS] + "... and more, check the screen for the rest."
    speak(text)
    return True


# --------------------------------------------------
# STOPWATCH
# --------------------------------------------------

def _format_duration(seconds):
    """Turn a number of seconds into a spoken-friendly string like '2 minutes, 5 seconds'."""
    seconds = int(round(seconds))
    hrs, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if hrs:
        parts.append(f"{hrs} hour{'s' if hrs != 1 else ''}")
    if mins:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return ", ".join(parts)


def start_stopwatch():
    global _stopwatch_start
    _stopwatch_start = time.time()
    speak("Stopwatch started.")


def stop_stopwatch():
    global _stopwatch_start
    if _stopwatch_start is None:
        speak("The stopwatch isn't running.")
        return
    elapsed = time.time() - _stopwatch_start
    _stopwatch_start = None
    speak(f"Stopped. Elapsed time: {_format_duration(elapsed)}.")


# --------------------------------------------------
# COUNTDOWN TIMER
# --------------------------------------------------

def parse_duration_command(command):
    """
    Pull a duration out of a command like 'timer for 2 minutes' or
    'set a timer for 90 seconds'. Returns (seconds, spoken_label) or
    (None, None) if nothing was found.
    """
    match = re.search(r"(\d+)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)", command)
    if not match:
        return None, None

    value = int(match.group(1))
    unit = match.group(2)

    if unit.startswith("h"):
        seconds, unit_label = value * 3600, "hour" if value == 1 else "hours"
    elif unit.startswith("m"):
        seconds, unit_label = value * 60, "minute" if value == 1 else "minutes"
    else:
        seconds, unit_label = value, "second" if value == 1 else "seconds"

    return seconds, f"{value} {unit_label}"


def _ring_alarm(label):
    """Beep a few times (if possible) then announce the timer is done."""
    if HAS_WINSOUND:
        try:
            for _ in range(6):
                winsound.Beep(1000, 400)
                time.sleep(0.15)
        except Exception as e:
            print(f"Alarm beep error: {e}")
    speak(f"Time's up! Your {label} timer is done.")


def start_timer(seconds, label):
    """Start a countdown timer that rings after `seconds`, without blocking nexon."""
    def _on_ring():
        _ring_alarm(label)
        if timer in _active_timers:
            _active_timers.remove(timer)

    timer = threading.Timer(seconds, _on_ring)
    timer.daemon = True
    timer.start()
    _active_timers.append(timer)
    speak(f"Timer set for {label}.")


def cancel_all_timers():
    global _active_timers
    if not _active_timers:
        speak("No timers are running.")
        return
    for t in _active_timers:
        t.cancel()
    _active_timers = []
    speak("Timers cancelled.")


# --------------------------------------------------
# SYSTEM CONTROLS
# --------------------------------------------------

def volume_up():
    # Windows/Linux/macOS keyboard media key
    pyautogui.press("volumeup", presses=VOLUME_STEP)


def volume_down():
    pyautogui.press("volumedown", presses=VOLUME_STEP)


def mute():
    pyautogui.press("volumemute")


def set_volume(level):
    """Set system volume to an exact percentage (0-100). Windows only (pycaw)."""
    level = max(0, min(100, level))
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100, None)
    except Exception as e:
        print(f"Volume error: {e}")


def next_video():
    pyautogui.hotkey("shift", "n")


def previous_video():
    pyautogui.hotkey("shift", "p")


def play_pause():
    pyautogui.press("space")


def _find_and_click_skip_button():
    """
    One OCR pass over the screen: look for a word containing 'skip'.
    Skip clicking if a digit sits close by on the same line (e.g.
    'Skip Ad in 4'), since that means the button isn't clickable yet.
    Only digits *near* the skip word count - Tesseract groups text into
    "lines" purely by vertical position, so an unrelated timestamp (e.g.
    the video's current playback time) sitting at the same height on the
    other side of the screen would otherwise be mistaken for a countdown
    and block every click for the whole ad.
    Returns True if it clicked something.
    """
    screenshot = pyautogui.screenshot()
    try:
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"OCR error: {e}")
        return False

    n = len(data["text"])

    for i, word in enumerate(data["text"]):
        if "skip" not in word.lower().strip():
            continue

        skip_left = data["left"][i]
        skip_width = data["width"][i]
        skip_height = data["height"][i]
        skip_right = skip_left + skip_width
        line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])

        # Only words physically near "skip" on the same line count as
        # part of its countdown - not anything else sharing that line.
        nearby_has_digit = False
        for j in range(n):
            if j == i:
                continue
            if (data["block_num"][j], data["par_num"][j], data["line_num"][j]) != line_key:
                continue
            if not data["text"][j].strip():
                continue
            distance = abs(data["left"][j] - skip_right)
            if distance > max(skip_width * 4, 150):
                continue  # too far away to be part of this button
            if re.search(r"\d", data["text"][j]):
                nearby_has_digit = True
                break

        if nearby_has_digit:
            continue  # still counting down ("Skip Ad in 4") - not clickable yet

        x = skip_left + skip_width // 2
        y = data["top"][i] + skip_height // 2
        pyautogui.click(x, y)
        return True

    return False


def _skip_ad_worker(max_wait=20, poll_interval=1.5):
    start = time.time()
    while time.time() - start < max_wait:
        if _find_and_click_skip_button():
            speak("Skipped the ad.")
            return
        time.sleep(poll_interval)
    speak("I couldn't find a skip button.")


def skip_ad():
    """
    Look for a 'Skip Ad' button on screen (via OCR) and click it. Polls
    for a while in the background since skippable ads usually only become
    clickable a few seconds in.
    """
    speak("Looking for a skip button.")
    threading.Thread(target=_skip_ad_worker, daemon=True).start()


def brightness_up():
    try:
        current = sbc.get_brightness(display=0)[0]
        new_value = min(100, current + BRIGHTNESS_STEP)
        sbc.set_brightness(new_value)

    except Exception as e:
        print(f"Brightness error: {e}")


def brightness_down():
    try:
        current = sbc.get_brightness(display=0)[0]
        new_value = max(0, current - BRIGHTNESS_STEP)
        sbc.set_brightness(new_value)

    except Exception as e:
        print(f"Brightness error: {e}")


def set_brightness(level):
    """Set screen brightness to an exact percentage (0-100)."""
    level = max(0, min(100, level))
    try:
        sbc.set_brightness(level)
    except Exception as e:
        print(f"Brightness error: {e}")


scrshot_counter = 1
SCREENSHOT_PATH = fr"C:\Users\rabey\OneDrive\Pictures\nexonScreenshot\Screenshot{scrshot_counter}.png"


def take_screenshot():
    global scrshot_counter
    screenshot = pyautogui.screenshot()
    screenshot.save(SCREENSHOT_PATH)
    print(f"Screenshot saved to: {SCREENSHOT_PATH}")
    scrshot_counter += 1
    speak("Screenshot saved.")


# --------------------------------------------------
# FILE OPERATIONS
# --------------------------------------------------

def delete_selected_file(permanent=False):
    """
    Delete whatever file/item is currently selected (e.g. after
    "click <filename>" selected it via OCR). This is just a keystroke
    sent to whichever window has focus - it deletes the selected item in
    File Explorer, but in another app Delete/Shift+Delete will do
    whatever THAT app maps it to. Make sure File Explorer, with the right
    item selected, is the focused window before using this.

    permanent=False (default) sends plain Delete, which moves the item to
    the Recycle Bin. permanent=True sends Shift+Delete, which skips the
    Recycle Bin entirely - Windows may pop up a confirmation dialog for
    this ("Are you sure you want to permanently delete this file?"),
    which nexon does not click through for you.
    """
    if permanent:
        pyautogui.hotkey("shift", "delete")
        speak("Permanently deleted.")
    else:
        pyautogui.press("delete")
        speak("Moved to Recycle Bin.")


def clear_recycle_bin():
    """
    Empty the Windows Recycle Bin via a direct call into shell32
    (SHEmptyRecycleBinW) - no confirmation dialog, progress window, or
    sound. Windows only.
    """
    try:
        import ctypes
        SHERB_NOCONFIRMATION = 0x00000001
        SHERB_NOPROGRESSUI = 0x00000002
        SHERB_NOSOUND = 0x00000004
        flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        # 0 = success. -2147418113 (0x8000FFFF) shows up on some Windows
        # versions when the bin was already empty - not a real failure.
        if result not in (0, -2147418113):
            raise OSError(f"SHEmptyRecycleBinW returned {result}")
    except AttributeError:
        speak("Emptying the Recycle Bin only works on Windows.")
        return False
    except Exception as e:
        print(f"Recycle bin error: {e}")
        speak("I couldn't empty the Recycle Bin.")
        return False

    speak("Recycle Bin emptied.")
    return True


import requests
from bs4 import BeautifulSoup

def google_search(query, read_result=True):
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
    webbrowser.open(url) 
    if not read_result:
        return

    speak(f"Searching for {query}.")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
    except Exception as e:
        print(f"Search fetch error: {e}")
        speak("I opened the search, but couldn't fetch the results to read aloud.")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    result = next((b for b in soup.select("div.g") if b.find("h3")), None)
    if result is None:
        speak("I opened the search, but couldn't find a readable result.")
        return

    title = result.find("h3").get_text(strip=True)
    snippet_tag = result.find("span")
    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
    speak_long_text(f"{title}. {snippet}" if snippet else title, prefix="Top result:")

# --------------------------------------------------
# PDF READING
# --------------------------------------------------

def _get_active_window_title():
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""


def _normalize_for_match(text):
    """
    Lowercase and collapse punctuation/underscores/hyphens down to single
    spaces, so 'Project_Proposal-Final (v2).pdf' and 'project proposal
    final v2' compare the same way.
    """
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def _find_pdf_file(hint):
    """
    Search PDF_SEARCH_DIRS for a PDF matching `hint`. Matching is fuzzy on
    purpose, since spoken filenames rarely line up exactly with how a file
    is actually named on disk:

      1. Exact normalized substring match (best) - e.g. hint "project
         proposal" matches "Project_Proposal_Final.pdf".
      2. All hint words present somewhere in the filename, any order.
      3. Fallback: similarity-ratio fuzzy match, for typos/mis-hearings,
         accepted only above PDF_FUZZY_MATCH_THRESHOLD.

    Returns the single best matching path, or None.
    """
    hint_norm = _normalize_for_match(hint)
    if not hint_norm:
        return None
    hint_words = hint_norm.split()

    best_path = None
    best_rank = None  

    for folder in PDF_SEARCH_DIRS:
        if not os.path.isdir(folder):
            continue
        for path in glob.glob(os.path.join(folder, "**", "*.pdf"), recursive=True):
            base_norm = _normalize_for_match(os.path.splitext(os.path.basename(path))[0])
            if not base_norm:
                continue
            base_words = base_norm.split()

            if hint_norm in base_norm:
                rank = (0, 0)
            elif all(w in base_words for w in hint_words):
                rank = (1, 0)
            else:
                similarity = difflib.SequenceMatcher(None, hint_norm, base_norm).ratio()
                if similarity < PDF_FUZZY_MATCH_THRESHOLD:
                    continue
                rank = (2, -similarity)

            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_path = path

    return best_path


def _locate_pdf(name_hint=None):
    """
    Figure out which PDF file to open: use a spoken filename hint if given,
    otherwise try to guess from the active window's title bar (most PDF
    viewers put the filename there).
    """
    if name_hint:
        found = _find_pdf_file(name_hint)
        if found:
            return found

    title = _get_active_window_title()
    match = re.search(r"([\w,\s\-\_\(\)]+\.pdf)", title, re.IGNORECASE)
    if match:
        return _find_pdf_file(os.path.splitext(match.group(1))[0])

    return None


def open_pdf(name_hint=None):
    """Locate and open a PDF, resetting page position to the start."""
    global _pdf_state

    path = _locate_pdf(name_hint)
    if not path:
        speak("I couldn't find that PDF. Make sure it's in Desktop, Documents, or Downloads.")
        return False

    try:
        doc = pymupdf.open(path)
    except Exception as e:
        print(f"PDF open error: {e}")
        speak("I couldn't open that PDF.")
        return False

    _pdf_state = {"path": path, "doc": doc, "page": 0}
    speak(f"Opened {os.path.basename(path)}. {doc.page_count} pages.")
    return True


def launch_pdf_file(name_hint=None):
    """
    Find a PDF by (partial, fuzzy) filename and open it in the system's
    default PDF viewer - like double-clicking it in Explorer. Unlike
    open_pdf()/read_pdf_page(), this does NOT load the file into nexon's
    own reader state; it's for when you just want the file up on screen.
    Windows only (os.startfile).
    """
    path = _locate_pdf(name_hint)
    if not path:
        speak("I couldn't find that PDF. Make sure it's in Desktop, Documents, or Downloads.")
        return False

    try:
        os.startfile(path)
    except AttributeError:
        # os.startfile only exists on Windows
        speak("Launching files in their default viewer only works on Windows.")
        return False
    except Exception as e:
        print(f"PDF launch error: {e}")
        speak("I found the file but couldn't open it.")
        return False

    speak(f"Opening {os.path.basename(path)}.")
    return True


def _ocr_pdf_page(page):
    """OCR fallback for a PDF page with no extractable text (e.g. a scan)."""
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        print(f"OCR error: {e}")
        return ""


def read_pdf_page(page_number=None):
    """Read the current (or given) page of the currently open PDF aloud."""
    global _pdf_state

    doc = _pdf_state["doc"]
    if doc is None:
        speak("No PDF is open. Say 'read screen' with a PDF focused, or 'read pdf' and the filename.")
        return

    index = page_number - 1 if page_number is not None else _pdf_state["page"]

    if index < 0 or index >= doc.page_count:
        speak("That page doesn't exist.")
        return

    _pdf_state["page"] = index
    text = doc[index].get_text().strip()

    if not text:
        text = _ocr_pdf_page(doc[index])

    if not text:
        speak(f"Page {index + 1} doesn't seem to have any readable text.")
        return

    speak_long_text(text, prefix=f"Page {index + 1} of {doc.page_count}.")


def next_pdf_page():
    if _pdf_state["doc"] is None:
        speak("No PDF is open.")
        return
    _pdf_state["page"] += 1
    read_pdf_page()


def previous_pdf_page():
    if _pdf_state["doc"] is None:
        speak("No PDF is open.")
        return
    _pdf_state["page"] = max(0, _pdf_state["page"] - 1)
    read_pdf_page()


# --------------------------------------------------
# SCREEN READING (OCR)
# --------------------------------------------------

def read_screen():
    """
    Read what's currently on screen. If the active window looks like a PDF
    viewer, read the actual PDF text directly (accurate, tracks page
    position for 'next page'/'previous page'). Otherwise, fall back to
    OCR-ing the whole screen.
    """
    title = _get_active_window_title()

    if ".pdf" in title.lower():
        if open_pdf():
            read_pdf_page()
            return
        speak("I see a PDF window but couldn't locate the file. Reading the screen instead.")

    screenshot = pyautogui.screenshot()
    try:
        text = pytesseract.image_to_string(screenshot)
    except Exception as e:
        print(f"OCR error: {e}")
        speak("I couldn't read the screen. Is Tesseract installed?")
        return

    if not speak_long_text(text, prefix="Here's what I see on screen."):
        speak("I couldn't find any readable text on screen.")


# --------------------------------------------------
# CLICK ON SCREEN (OCR)
# --------------------------------------------------
#
# Generalizes the OCR-and-click trick already used by
# _find_and_click_skip_button() into something reusable for any labeled
# button, link, video title, or menu item. It CANNOT click bare icons or
# unlabeled thumbnails - there's no OCR text there to match against.

def _ocr_screen_words():
    """One OCR pass over the whole screen. Returns pytesseract's word-level dict, or None on failure."""
    screenshot = pyautogui.screenshot()
    try:
        return pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"OCR error: {e}")
        return None


def _find_clickable_text(target, data, screenshot_size=None):
    """
    Group OCR'd words into lines and find the best match for `target`.

    The returned point is scaled from the screenshot's pixel coordinates to
    PyAutoGUI's screen coordinates. This matters on Windows when display
    scaling/DPI settings cause screenshot pixels and mouse coordinates to
    use different dimensions.
    """
    target_norm = _normalize_for_match(target)
    if not target_norm:
        return None

    lines = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    best_idxs, best_rank = None, None
    for idxs in lines.values():
        line_norm = _normalize_for_match(" ".join(data["text"][i] for i in idxs))
        if not line_norm:
            continue

        if target_norm in line_norm:
            rank = (0, 0)
        elif all(w in line_norm.split() for w in target_norm.split()):
            rank = (1, 0)
        else:
            sim = difflib.SequenceMatcher(None, target_norm, line_norm).ratio()
            if sim < PDF_FUZZY_MATCH_THRESHOLD:
                continue
            rank = (2, -sim)

        if best_rank is None or rank < best_rank:
            best_rank, best_idxs = rank, idxs

    if best_idxs is None:
        return None

    left = min(data["left"][i] for i in best_idxs)
    top = min(data["top"][i] for i in best_idxs)
    right = max(data["left"][i] + data["width"][i] for i in best_idxs)
    bottom = max(data["top"][i] + data["height"][i] for i in best_idxs)

    # Click the center of the complete OCR line, then convert from
    # screenshot pixels to actual mouse coordinates if Windows DPI scaling
    # makes those coordinate systems different.
    x = (left + right) / 2
    y = (top + bottom) / 2

    if screenshot_size:
        screen_w, screen_h = pyautogui.size()
        shot_w, shot_h = screenshot_size
        if shot_w and shot_h:
            x *= screen_w / shot_w
            y *= screen_h / shot_h

    return round(x), round(y)


def click_on_screen(target, double=False):
    """
    OCR the screen, find text matching `target`, and click its center.
    Works for anything with visible text: a labeled button, a link, a
    video title, a menu item. Does NOT work on unlabeled icons/thumbnails
    since there's no OCR text there to match against.
    """
    target = (target or "").strip()
    if not target:
        speak("What should I click?")
        return False

    screenshot = pyautogui.screenshot()
    try:
        data = pytesseract.image_to_data(
            screenshot,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        print(f"OCR error: {e}")
        speak("I couldn't read the screen.")
        return False

    point = _find_clickable_text(target, data, screenshot.size)
    if point is None:
        speak(f"I couldn't find anything on screen that says {target}.")
        return False

    # Move first so the target location is stable before clicking.
    pyautogui.moveTo(*point, duration=CLICK_MOVE_DURATION)

    if double:
        pyautogui.doubleClick(
            *point,
            interval=DOUBLE_CLICK_INTERVAL,
            duration=0
        )
        speak(f"Double clicked {target}.")
    else:
        pyautogui.click(*point)
        speak(f"Clicked {target}.")

    return True


def scroll_up(amount=SCROLL_STEP):
    amount = 300
    pyautogui.scroll(amount)


def scroll_down(amount=SCROLL_STEP):
    amount = 300
    pyautogui.scroll(-amount)


def type_text(text, press_enter=False):
    """
    Type `text` into whatever currently has focus - search bar, address
    bar, form field, anything. press_enter=True submits afterward.
    """
    keyboard.write(text, delay=0.01)
    if press_enter:
        pyautogui.press("enter")

def read_whatsapp():
    """
    Screenshot just the WhatsApp Desktop window and OCR it, then speak
    only the parts that weren't there last time (a rough 'new messages' check).
    Requires WhatsApp Desktop to be open.
    """
    global _last_whatsapp_text

    try:
        windows = gw.getWindowsWithTitle("WhatsApp")
        if not windows:
            speak("I can't find an open WhatsApp window.")
            return
        win = windows[0]
        win.activate()
        time.sleep(0.5)

        region = (win.left, win.top, win.width, win.height)
        screenshot = pyautogui.screenshot(region=region)
        text = pytesseract.image_to_string(screenshot).strip()

    except Exception as e:
        print(f"WhatsApp read error: {e}")
        speak("I had trouble reading WhatsApp.")
        return

    if not text:
        speak("I couldn't read anything from WhatsApp.")
        return

    if text == _last_whatsapp_text:
        speak("No new messages since I last checked.")
        return

    _last_whatsapp_text = text
    speak_long_text(text, prefix="Here's what's currently showing in WhatsApp.")


# --------------------------------------------------
# DICTATION / TYPING INTO CHATS
# --------------------------------------------------

def dictate_and_type(existing_text=None, send=False):
    """
    Type spoken text into whatever text field currently has focus
    (e.g. click into a WhatsApp/browser chat box first, then say
    'nexon type <message>' or just 'nexon dictate').
    If send=True, presses Enter afterward.
    """
    if existing_text:
        text_to_type = existing_text
    else:
        speak("Go ahead, I'm listening.")
        text_to_type = listen_raw()

    if not text_to_type:
        speak("I didn't catch that.")
        return

    pyautogui.write(text_to_type, interval=0.02)
    if send:
        pyautogui.press("enter")
        speak("Sent.")
    else:
        speak("Typed it.")


# --------------------------------------------------
# WEB BROWSER
# --------------------------------------------------

def open_website(command):
    """Handle 'open <site>' by matching shortcuts or building a URL."""
    match = re.search(r"open (.+)", command)
    if not match:
        speak("Which website should I open?")
        return

    site = match.group(1).strip().rstrip(".")

    if site in SITE_SHORTCUTS:
        url = SITE_SHORTCUTS[site]
    elif site.startswith("http://") or site.startswith("https://"):
        url = site
    elif "." in site:
        url = f"https://{site}"
    else:
        url = f"https://{site}.com"

    webbrowser.open(url)
    speak(f"Opening {site}")


def close_tab():
    """
    Close the current tab (Ctrl+W). This is just a keystroke sent to
    whatever window has focus - it closes a browser tab if a browser is
    focused, but in another app it'll do whatever that app maps Ctrl+W to
    (often closing a document/window). Make sure a browser is focused.
    """
    pyautogui.hotkey("ctrl", "w")


def close_all_tabs():
    """
    Close all tabs in the current browser window (Ctrl+Shift+W). In most
    browsers this closes the entire window rather than closing tabs one
    at a time and leaving the window open - there's no universal
    keyboard-only way to do the latter across browsers. Only use this
    with a browser focused.
    """
    pyautogui.hotkey("ctrl", "shift", "w")


def play_on_youtube(command):
    """Handle 'play <song/query> [on youtube]' by auto-playing the top result."""
    match = re.search(r"play (.+?)(?: on youtube)?$", command)
    query = match.group(1).strip() if match else command.replace("play", "", 1).strip()

    if not query:
        speak("What should I play?")
        return

    speak(f"Playing {query} on YouTube")
    try:
        pywhatkit.playonyt(query)
    except Exception as e:
        print(f"YouTube play error: {e}")
        speak("I couldn't play that on YouTube.")


# --------------------------------------------------
# COMMAND PROCESSING
# --------------------------------------------------

def process_command(command):

    if not command:
        return True

    # ---- COUNTDOWN TIMER (checked before the stopwatch's plain "start/stop
    #      timer" so "start a timer for 5 minutes" doesn't get swallowed by
    #      the stopwatch branch below) ----

    if "timer for" in command or re.search(r"set (a |an )?timer", command):
        seconds, label = parse_duration_command(command)
        if seconds:
            start_timer(seconds, label)
        else:
            speak("How long should I set the timer for?")

    elif "cancel timer" in command or "cancel timers" in command or "stop the timer" in command:
        cancel_all_timers()

    # ---- STOPWATCH ----

    elif "start timer" in command or "start stopwatch" in command:
        start_stopwatch()

    elif "stop timer" in command or "stop stopwatch" in command:
        stop_stopwatch()

    # ---- SET VOLUME / BRIGHTNESS (checked so "set volume to 50"
    #      isn't swallowed by the plain "volume up"/"volume down" checks) ----

    elif "set volume" in command or "volume to" in command:
        level = extract_number(command)
        if level is not None:
            set_volume(level)
            speak(f"Volume set to {level}")
        else:
            speak("I didn't catch the volume level.")

    elif "set brightness" in command or "brightness to" in command:
        level = extract_number(command)
        if level is not None:
            set_brightness(level)
            speak(f"Brightness set to {level}")
        else:
            speak("I didn't catch the brightness level.")

    # ---- SCREEN / WHATSAPP / PDF READING ----

    elif "read whatsapp" in command or "whatsapp messages" in command or "new messages" in command:
        read_whatsapp()

    # "launch pdf <name>" / "open pdf <name>" - open in the default viewer.
    # Checked before "read pdf" doesn't matter (different prefixes), but it
    # MUST be checked before the generic "open " website branch further
    # down, or "open pdf ..." would get treated as a website.
    elif command.startswith("launch pdf") or command.startswith("open pdf"):
        hint = re.sub(r"^(launch|open) pdf", "", command).strip()
        launch_pdf_file(hint or None)

    elif command.startswith("read pdf"):
        hint = command[len("read pdf"):].strip()
        if open_pdf(hint or None):
            read_pdf_page()

    elif "read page" in command:
        num = extract_number(command)
        read_pdf_page(num)

    elif "next page" in command:
        next_pdf_page()

    elif "previous page" in command or "last page" in command or "go back a page" in command:
        previous_pdf_page()

    elif "read screen" in command or "what's on my screen" in command or "whats on my screen" in command or "read the screen" in command:
        read_screen()

    # ---- SCROLLING ----
    # Positive pyautogui.scroll() = up; negative = down.
    # Optional numbers let you say "scroll down 3".
    elif "scroll up" in command:
        amount = extract_number(command) or SCROLL_STEP
        scroll_up(amount)
        speak("Scrolled up")

    elif "scroll down" in command:
        amount = extract_number(command) or SCROLL_STEP
        scroll_down(amount)
        speak("Scrolled down")

    # ---- CLICK ON SCREEN (OCR) ----
    # "double click" is checked first so it can never be swallowed by the
    # plain "click " branch below.

    elif command.startswith("double click "):
        click_on_screen(command[len("double click "):].strip(), double=True)

    elif command.startswith("click "):
        click_on_screen(command[len("click "):].strip())

    # ---- FILE OPERATIONS ----
    # Assumes the file/item is already selected on screen (e.g. via a
    # prior "click <filename>"). "permanently"/"forever" in the phrase
    # sends Shift+Delete instead of plain Delete.

    elif "clear recycle bin" in command or "empty recycle bin" in command or "clear the recycle bin" in command or "empty the recycle bin" in command or "empty the bin" in command or "clear the bin" in command or "empty bin" in command or "clear bin" in command:
        clear_recycle_bin()

    elif "delete file" in command or "delete this file" in command or "delete the file" in command or command.strip() == "delete":
        permanent = "permanently" in command or "forever" in command
        delete_selected_file(permanent=permanent)

    # ---- DICTATION / TYPING ----
    # "type <message>" types immediately; bare "dictate"/"type a message"
    # prompts and listens for the message separately, so it works even
    # if the phrase itself contains words like "type" mid-sentence.
    #
    # "type <text> and search" / "type <text> and enter" is the generic
    # version of "send message" for non-chat fields like a search bar:
    # it fills the focused field and submits, without implying you're
    # sending a chat message. Checked before the plain "type " branch so
    # the suffix gets stripped and handled by type_text() instead.

    elif command.startswith("send message") or command.startswith("send a message"):
        text_after = re.sub(r"^send( a)? message", "", command).strip()
        dictate_and_type(existing_text=text_after or None, send=True)

    elif command.startswith("type ") and command.endswith((" and enter", " and search")):
        text_after = re.sub(r"\s+and (enter|search)$", "", command[len("type "):]).strip()
        type_text(text_after, press_enter=True)

    elif command.startswith("type "):
        text_after = command[len("type "):].strip()
        dictate_and_type(existing_text=text_after or None, send=False)

    elif "dictate" in command or command.strip() == "type a message":
        dictate_and_type(send=False)

    # ---- WEB BROWSER ----

    elif command.startswith("search "):
        google_search(command[len("search "):].strip())

    elif command.startswith("play "):
        play_on_youtube(command)

    elif command.startswith("open "):
        open_website(command)

    # Checked BEFORE the single-tab branch below, on purpose: "close all
    # tabs" must never fall into "close tab" (or vice versa).
    elif "close all tab" in command:
        close_all_tabs()
        speak("Closed all tabs")

    elif "close tab" in command or "close this tab" in command or "close the tab" in command or "close current tab" in command:
        close_tab()
        speak("Closed the tab")

    # ---- MEDIA ----

    elif "next video" in command or command == "next":
        next_video()
        speak("Next video")

    elif "previous video" in command or "last video" in command:
        previous_video()
        speak("Previous video")

    elif "skip ad" in command or "skip the ad" in command or "skip this ad" in command or "skip ads" in command:
        skip_ad()

    elif "pause" in command or "play" in command:
        play_pause()
        speak("Okay")

    # ---- VOLUME ----

    elif "volume up" in command or "increase volume" in command:
        volume_up()
        speak("Volume up")

    elif "volume down" in command or "decrease volume" in command:
        volume_down()
        speak("Volume down")

    elif "mute" in command:
        mute()
        speak("Muted")

    # ---- BRIGHTNESS ----

    elif "brightness up" in command or "increase brightness" in command:
        brightness_up()
        speak("Brightness up")

    elif "brightness down" in command or "decrease brightness" in command:
        brightness_down()
        speak("Brightness down")

    elif "screenshot" in command or "take a screenshot" in command:
        take_screenshot()
    

    # ---- EXIT ----

    elif (
        "shutdown assistant" in command
        or "exit" in command
        or "quit" in command
        or "goodbye" in command
    ):
        speak("Goodbye.")
        return False

    else:
        speak("I don't know that command yet.")

    return True


# --------------------------------------------------
# MAIN LOOP
# --------------------------------------------------

def main():

    global _stay_awake

    print("--------------------------------")
    print(" nexon voice assistant")
    print("--------------------------------")
    print(f"Wake word: {WAKE_WORD}")
    print("Say 'nexon' to activate.")
    print("Say 'nexon awake' to stop needing the wake word each time.")
    print("Say 'sleep' (while awake) or 'nexon sleep' to go back to normal.")
    print("Say 'shutdown assistant' to quit.")
    print()

    # Starts one continuously-open mic stream on its own background
    # thread (includes the ambient-noise calibration that used to happen
    # here directly) - this replaces the old "open mic, listen, close
    # mic, repeat" loop, so there's no gap where nexon isn't listening.
    stop_listening = start_background_listening()

    speak("nexon is ready.")

    running = True

    try:
        while running:

            # Pull the next recognized phrase off the queue. A short
            # timeout just keeps this loop responsive (e.g. to Ctrl+C);
            # the mic itself is always listening regardless of this.
            heard = get_heard(timeout=0.2)

            if not heard:
                continue

            # ------------------------------------------
            # STAY-AWAKE MODE: no wake word needed. Every
            # heard phrase is tried directly as a command.
            # ------------------------------------------

            if _stay_awake:

                # If old habits kick in and "nexon" still gets said, strip it
                # off so e.g. "nexon next video" still works while awake.
                spoken = heard.split(WAKE_WORD, 1)[1].strip() if WAKE_WORD in heard else heard

                if not spoken:
                    continue

                if any(phrase in spoken for phrase in SLEEP_PHRASES):
                    _stay_awake = False
                    speak("Going back to sleep. Say nexon to wake me up.")
                    continue

                running = process_command(spoken)
                continue

            # ------------------------------------------
            # NORMAL MODE: wake word required
            # ------------------------------------------

            if WAKE_WORD in heard:

                # If you said:
                # "nexon next video"
                # we can use the rest immediately.

                command = heard.split(WAKE_WORD, 1)[1].strip()

                if not command:
                    speak("Yes?")
                    # Wait for the follow-up command to arrive on the
                    # queue - the mic never stopped listening in the
                    # meantime, so nothing said right after "Yes?" is lost.
                    command = get_heard(timeout=COMMAND_TIMEOUT)

                if command and any(phrase in command for phrase in STAY_AWAKE_PHRASES):
                    _stay_awake = True
                    speak("I'll stay awake. Just say sleep, or nexon sleep, when you want me to stop.")
                elif command:
                    running = process_command(command)
    finally:
        stop_listening(wait_for_stop=False)


if __name__ == "__main__":
    main()