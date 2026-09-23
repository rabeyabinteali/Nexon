"""
COMMANDS: media

  "next video" / "next"                 -> Shift+N
  "previous video" / "last video"       -> Shift+P
  "skip ad" (and mishearings)           -> OCR-find and click a skip button
  "pause" / "play"                      -> Space

IMPORTANT ordering note: this module is imported (see commands/__init__)
AFTER nexon.commands.browser, so "play <song> [on youtube]" is claimed
there first - otherwise it would be swallowed by the generic "play"
check here.
"""

import re
import threading
import time

import pyautogui

from .. import ocr
from ..registry import command
from ..tts import speak


def next_video():
    pyautogui.hotkey("shift", "n")


def previous_video():
    pyautogui.hotkey("shift", "p")


def play_pause():
    pyautogui.press("space")

def full_screen():
    pyautogui.press("F")

def is_skip_ad_command(command_text):
    """True for "skip ad", "skip the ad", "skip ads", and common mishearings like "skip add" / "skip a d"."""
    if any(phrase in command_text for phrase in ("skip ad", "skip the ad", "skip this ad", "skip ads")):
        return True
    return bool(re.search(r"\bskip(ped)?\b(\s+(the|this|that|an|a))?\s+(ad|ads|add|adds|a d)\b", command_text))


def _skip_ad_worker(max_wait=20, poll_interval=1.5):
    start = time.time()
    while time.time() - start < max_wait:
        if ocr.find_and_click_skip_button():
            speak("Skipped the ad.")
            return
        time.sleep(poll_interval)
    speak("I couldn't find a skip button.")


def skip_ad():
    """
    Look for a 'Skip Ad' button on screen (via OCR) and click it. Polls
    for a while in the background since skippable ads usually only
    become clickable a few seconds in.
    """
    speak("Looking for a skip button.")
    threading.Thread(target=_skip_ad_worker, daemon=True).start()


# ---- registered commands, in original priority order ----

@command(lambda cmd: "next video" in cmd or cmd == "next")
def handle_next_video(command_text):
    next_video()
    speak("Next video", wait=False)


@command(["previous video", "last video"])
def handle_previous_video(command_text):
    previous_video()
    speak("Previous video", wait=False)


@command(is_skip_ad_command)
def handle_skip_ad(command_text):
    skip_ad()


@command(lambda cmd: "pause" in cmd or "play" in cmd)
def handle_play_pause(command_text):
    play_pause()
    speak("Okay", wait=False)


@command(lambda cmd: "fullscreen" in cmd)
def handle_play_pause(command_text):
    full_screen()
    speak("Okay", wait=False)

