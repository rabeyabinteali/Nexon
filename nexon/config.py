"""
nexon.config
------------
Every tunable setting nexon has, in one place. Nothing in here talks to
the mic, the screen, or the network - it's just numbers, strings, and
lookup tables that the rest of the package imports.
"""

import os

try:
    import winsound  # stdlib, Windows only - used to ring the countdown timer
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# If Tesseract isn't on PATH, set this. Leave as None to use PATH as-is.
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --------------------------------------------------
# WAKE WORD / LISTENING MODE
# --------------------------------------------------

WAKE_WORD = "nexon"

# Phrases (heard AFTER the wake word) that toggle "awake" mode, where
# nexon stops requiring the wake word before every command and just tries
# to match anything it hears against a command instead.
STAY_AWAKE_PHRASES = ("awake", "keep listening", "always listen", "start listen", "keep listen")

# Phrases that drop nexon back out of "awake" mode into the normal
# wake-word-required state. Checked WITHOUT needing "nexon" first while
# already in awake mode (that's the whole point).
SLEEP_PHRASES = ("sleep", "go to sleep", "stop listening")

# How long nexon waits for you to actually say the command after it
# replies "Yes?" (you said just the wake word with nothing after it)
COMMAND_TIMEOUT = 10

# Safety ceiling on how long a single phrase can run in the ALWAYS-ON
# background listener before it's cut and sent off for recognition
# regardless of whether you've paused. A phrase normally ends on its own
# after PAUSE_THRESHOLD seconds of silence; this just stops one from
# running forever if you never pause.
PHRASE_TIME_LIMIT = 30

# How long a pause (in seconds) ends a phrase and sends it off for
# recognition. Lower = commands start processing sooner; raise it back
# if long commands get cut at a mid-sentence pause.
PAUSE_THRESHOLD = 0.9

# Dictation (listen_raw) keeps a longer pause so mid-message breaths
# don't end the message early.
DICTATION_PAUSE_THRESHOLD = 1.4

# No ceiling at all for dictation - a message you're dictating should
# only end when you actually stop talking.
DICTATION_PHRASE_TIME_LIMIT = None

# Mic sample rate. Most mics default to 44100 Hz, which makes each clip
# ~2.7x bigger to upload than 16000 Hz. Set to None to use the mic's
# default rate always.
MIC_SAMPLE_RATE = 16000

# --------------------------------------------------
# SPEECH RECOGNITION
# --------------------------------------------------

# "auto"    = use Google (more accurate, no local model needed) whenever
#             the network looks fast enough, and switch to local
#             faster-whisper automatically when it's slow or
#             unreachable. Switches back to Google once the network
#             looks good again.
# "whisper" = always local (faster-whisper), typically well under a
#             second instead of 2-3s. Falls back to Google automatically
#             only if the local model can't load at all.
# "google"  = always the online recognizer, network conditions ignored.
RECOGNITION_ENGINE = "auto"

# --- only used when RECOGNITION_ENGINE == "auto" ---

# Quick up-front reachability check before ever calling Google: if this
# doesn't succeed within NETWORK_CHECK_TIMEOUT seconds, the network is
# treated as down for this cycle.
NETWORK_CHECK_HOST = ("8.8.8.8", 53)
NETWORK_CHECK_TIMEOUT = 1.0

# If an actual recognize_google() call takes longer than this many
# seconds, the network is treated as "slow" from here on (same as being
# unreachable) even though it technically returned an answer.
GOOGLE_SLOW_THRESHOLD = 3.0

# After the network is marked bad (unreachable OR slow), how long to
# keep using local recognition before trying Google again.
NETWORK_RECHECK_INTERVAL = 30

# Model size: "tiny.en" = fastest, "base.en" = good balance, "small.en" =
# most accurate but slower.
WHISPER_MODEL = "base.en"

# Whisper hears "nexon" as other things sometimes. Anything listed here is
# rewritten to the wake word (only applies to whisper results).
WAKE_WORD_VARIANTS = ("next on", "nixon", "nexan", "nexen", "nexxon", "nextron", "nexson")

# Hint text that nudges Whisper toward the wake word and your command
# vocabulary. Not used for dictation.
WHISPER_PROMPT = (
    f"{WAKE_WORD}. {WAKE_WORD}, next video. {WAKE_WORD}, volume up. "
    f"{WAKE_WORD}, read screen. Search, play, open, click, close tab, skip ad, set a timer."
)

# Prints how long each recognition takes (and, for Google, how big the
# upload was). Set to False once you're done tuning.
DEBUG_TIMING = True

# --------------------------------------------------
# SYSTEM CONTROLS
# --------------------------------------------------

VOLUME_STEP = 5
BRIGHTNESS_STEP = 10

# Mouse / scrolling controls
SCROLL_STEP = 5
CLICK_MOVE_DURATION = 0.08
DOUBLE_CLICK_INTERVAL = 0.15

# --------------------------------------------------
# OCR / SCREEN READING
# --------------------------------------------------

# How many characters of OCR'd text to actually speak aloud (long screens
# would otherwise take forever to read out)
MAX_SPOKEN_CHARS = 500

# Minimum similarity (0-1) accepted for a fuzzy filename/text match when
# no exact/word match is found. Lower = more forgiving, more false hits.
FUZZY_MATCH_THRESHOLD = 0.55

# OCR speed: screenshots wider than this are shrunk before Tesseract sees
# them (results are scaled back, so clicking still lands correctly).
OCR_MAX_WIDTH = 1920

# "skip ad" only scans the lower-right part of the screen, where the skip
# button lives. Fractions of screen width/height to cut off from the
# left/top. Set both to 0.0 to scan the whole screen again.
SKIP_SCAN_LEFT = 0.0
SKIP_SCAN_TOP = 0.25

# --------------------------------------------------
# SEARCH BAR AUTO-DETECT ("type ... and search")
# --------------------------------------------------

# OCR text tried (in this order) to guess where a page's/browser's
# search box is, so "nexon type cats and search" doesn't require
# clicking into the box yourself first. Best-effort: an icon-only
# search field (a bare magnifying glass, no placeholder text) can't be
# found this way, and the last, broadest entry ("search") could
# occasionally land on an unrelated on-page button/link that also says
# "search" - add more specific phrases above it if that happens on a
# site you use a lot.
SEARCH_BAR_HINTS = (
    "search or type",              # Chrome/Edge address bar placeholder
    "search google or type a url",
    "search the web",
    "type to search",
    "search this site",
    "search here",
    "search products",
    "search...",
    "search",                      # last resort - broadest, least reliable
)

# Pause after clicking into a found search bar, before selecting its
# existing text and typing - gives the field a moment to take focus.
SEARCH_BAR_CLICK_DELAY = 0.15

# --------------------------------------------------
# PDF READING
# --------------------------------------------------

# PDF filename index is cached instead of rescanning your folders on
# every command. Rebuilt after this many seconds, or once early if a PDF
# isn't found (in case you just added it).
PDF_INDEX_MAX_AGE = 300
PDF_INDEX_MIN_REFRESH = 30

# Folders searched (recursively) when trying to locate a PDF by filename
PDF_SEARCH_DIRS = [
    os.path.expanduser("C:/Users/rabey/Desktop"),
    os.path.expanduser("C:/Users/rabey/Documents"),
    os.path.expanduser("C:/Users/rabey/Downloads"),
]

# --------------------------------------------------
# WEB BROWSER
# --------------------------------------------------

# Common site shortcuts so "open youtube" works without saying ".com".
# Add new ones here - no other code needs to change.
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
    "ao3": "https://archiveofourown.org/",
    "archiveofourown": "https://archiveofourown.org/",
    "archive of our own": "https://archiveofourown.org/",
}

# --------------------------------------------------
# EMAIL
# --------------------------------------------------
#
# Uses only the standard library (imaplib + email) - free, no API key,
# works with any IMAP provider. Credentials are read from environment
# variables rather than hardcoded here, so they never end up committed
# to version control by accident.
#
# Gmail setup (free):
#   1. Turn on 2-Step Verification: myaccount.google.com/security
#   2. Create an App Password: myaccount.google.com/apppasswords
#      (your normal Google password will NOT work over IMAP)
#   3. Settings -> "Forwarding and POP/IMAP" -> Enable IMAP
#   4. Set the two environment variables below to your address and
#      that 16-character app password.
#
# Outlook/Yahoo/etc.: same idea (an app password once 2FA is on), just
# a different IMAP_HOST - see the README.

import os

IMAP_HOST = "imap.gmail.com"
IMAP_USER = os.environ.get("NEXON_EMAIL_USER", "")
IMAP_PASSWORD = os.environ.get("NEXON_EMAIL_PASSWORD", "")

# Folder/label names nexon checks for "check email". Gmail examples:
# "INBOX", "[Gmail]/Starred", or any label name you've created.
EMAIL_FOLDERS = ["INBOX"]

# Cap on how many unread emails get read aloud per "check email", so a
# swamped inbox doesn't turn into a five-minute monologue.
MAX_EMAILS_SPOKEN = 5

# --------------------------------------------------
# SCREENSHOTS
# --------------------------------------------------

SCREENSHOT_DIR = r"C:\Users\rabey\OneDrive\Pictures\nexonScreenshot"
