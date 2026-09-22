"""
nexon.helpers
-------------
Small, generic utilities with no state of their own - safe to import
from anywhere without creating circular imports.
"""

import re

from .config import MAX_SPOKEN_CHARS
from .tts import speak


def extract_number(command_text):
    """Pull the first integer out of a spoken command, e.g. 'set volume to 50' -> 50."""
    match = re.search(r"\d+", command_text)
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


def normalize_for_match(text):
    """
    Lowercase and collapse punctuation/underscores/hyphens down to single
    spaces, so 'Project_Proposal-Final (v2).pdf' and 'project proposal
    final v2' compare the same way. Used for both PDF filename matching
    and on-screen text matching (click_on_screen).
    """
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()
