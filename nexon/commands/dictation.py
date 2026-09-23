"""
COMMANDS: dictation / typing into whatever field has focus

  "send message [<text>]" / "send a message [<text>]"  -> types + Enter
  "type <text> and search"                              -> auto-locates a
                                                            search bar on
                                                            screen (OCR),
                                                            clicks into it,
                                                            then types +
                                                            Enter - no need
                                                            to click it
                                                            yourself first
  "type <text> and enter"                               -> types into
                                                            whatever
                                                            already has
                                                            focus + Enter
                                                            (both checked
                                                            BEFORE plain
                                                            "type " below)
  "type <text>"                                          -> types only
  "dictate" / "type a message"                           -> prompts, then
                                                             listens separately
"""

import re

from .. import ocr
from ..registry import command
from ..speech import listen_raw
from ..tts import speak

import pyautogui
import keyboard


def type_text(text, press_enter=False):
    """Type `text` into whatever currently has focus. press_enter=True submits afterward."""
    keyboard.write(text, delay=0.01)
    if press_enter:
        pyautogui.press("enter")


def type_into_search_bar(text, press_enter=True):
    """
    Best-effort: locate a search box on screen (OCR - see
    ocr.find_search_bar / config.SEARCH_BAR_HINTS) and click into it
    before typing, so 'type <x> and search' doesn't require clicking the
    search box yourself first. Falls back to typing wherever the
    cursor/focus already is if nothing on screen looked like a search box.
    """
    if not ocr.click_search_bar():
        speak("I couldn't spot a search bar - typing where the cursor already is.", wait=False)
    type_text(text, press_enter=press_enter)


def dictate_and_type(existing_text=None, send=False):
    """
    Type spoken text into whatever text field currently has focus (e.g.
    click into a chat box first, then say 'nexon type <message>' or just
    'nexon dictate'). If send=True, presses Enter afterward.
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


# ---- registered commands, in original priority order ----

@command(lambda cmd: cmd.startswith("send message") or cmd.startswith("send a message"))
def handle_send_message(command_text):
    text_after = re.sub(r"^send( a)? message", "", command_text).strip()
    dictate_and_type(existing_text=text_after or None, send=True)


@command(lambda cmd: cmd.startswith("type ") and cmd.endswith(" and search"))
def handle_type_and_search(command_text):
    text_after = re.sub(r"\s+and search$", "", command_text[len("type "):]).strip()
    type_into_search_bar(text_after, press_enter=True)


@command(lambda cmd: cmd.startswith("type ") and cmd.endswith(" and enter"))
def handle_type_and_submit(command_text):
    text_after = re.sub(r"\s+and enter$", "", command_text[len("type "):]).strip()
    type_text(text_after, press_enter=True)


@command(lambda cmd: cmd.startswith("type "))
def handle_type(command_text):
    text_after = command_text[len("type "):].strip()
    dictate_and_type(existing_text=text_after or None, send=False)


@command(lambda cmd: "dictate" in cmd or cmd.strip() == "type a message")
def handle_dictate(command_text):
    dictate_and_type(send=False)
