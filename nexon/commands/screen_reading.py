"""
COMMANDS: reading what's on screen

  "read whatsapp" / "new messages"           -> OCR the WhatsApp window
  "launch pdf <name>" / "open pdf <name>"    -> open in the default viewer
  "read pdf <name>"                          -> load into nexon's own reader
  "read page <N>"                            -> jump to page N (nexon's reader)
  "go to page <N>" / "jump to page <N>"      -> same, different phrasing
  "next page" / "next slide"                 -> advance a page
  "previous page" / "last page"              -> go back a page
  "read screen"                              -> OCR (or PDF-aware) read of
                                                 whatever's currently visible

IMPORTANT ordering note: this module is imported (see commands/__init__)
BEFORE nexon.commands.browser, because "launch pdf ..."/"open pdf ..."
must be claimed here before browser.py's generic "open <site>" handler
ever sees the command.
"""

import os
import re
import time

import keyboard
import pyautogui
import pygetwindow as gw
import pytesseract

from .. import pdf_reader
from ..config import TESSERACT_CMD
from ..helpers import extract_number, speak_long_text
from ..ocr import shrink_for_ocr
from ..registry import command
from ..tts import speak

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Remembers the last thing OCR'd from WhatsApp so we can tell what's new
_last_whatsapp_text = ""


def read_whatsapp():
    """
    Screenshot just the WhatsApp Desktop window and OCR it, then speak
    only the parts that weren't there last time (a rough 'new messages'
    check). Requires WhatsApp Desktop to be open.
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
# UNIVERSAL PAGE NAVIGATION
# --------------------------------------------------
#
# "next page"/"previous page" only use nexon's own page-turn-and-read-
# aloud logic when nexon actually has a PDF loaded internally
# (pdf_reader.has_open_pdf()). Otherwise they just send the standard
# page-turn keystroke to whichever window currently has focus - this
# makes them work generically (PDF viewers, browsers, PowerPoint, ebook
# readers...), at the cost of not being able to speak the new page's
# text aloud in that fallback case.

def handle_next_page_action():
    if pdf_reader.has_open_pdf():
        pdf_reader.next_pdf_page()
    else:
        pyautogui.press("pagedown")
        speak("Next page")


def handle_previous_page_action():
    if pdf_reader.has_open_pdf():
        pdf_reader.previous_pdf_page()
    else:
        pyautogui.press("pageup")
        speak("Previous page")


def handle_go_to_page_action(page_number):
    """
    'go to page X'. If nexon has a PDF loaded internally, jump straight
    there and read it aloud. Otherwise, best-effort generic jump: Ctrl+G
    is the "go to page" shortcut in most desktop PDF viewers (Adobe
    Reader, Foxit, SumatraPDF) - not universal (browsers' built-in PDF
    viewers don't support it), but the closest thing to a standard
    shortcut.
    """
    if page_number is None:
        speak("What page?")
        return

    if pdf_reader.has_open_pdf():
        pdf_reader.read_pdf_page(page_number)
    else:
        keyboard.send("ctrl+g")
        time.sleep(0.3)
        keyboard.write(str(page_number))
        keyboard.send("enter")
        speak(f"Going to page {page_number}")


def read_screen():
    """
    Read what's currently on screen. If the active window looks like a
    PDF viewer, read the actual PDF text directly (accurate, tracks page
    position for 'next page'/'previous page'). Otherwise, fall back to
    OCR-ing the whole screen.
    """
    title = pdf_reader.get_active_window_title()

    if ".pdf" in title.lower():
        if pdf_reader.open_pdf():
            pdf_reader.read_pdf_page()
            return
        speak("I see a PDF window but couldn't locate the file. Reading the screen instead.")

    screenshot = pyautogui.screenshot()
    try:
        text = pytesseract.image_to_string(shrink_for_ocr(screenshot)[0])
    except Exception as e:
        print(f"OCR error: {e}")
        speak("I couldn't read the screen. Is Tesseract installed?")
        return

    if not speak_long_text(text, prefix="Here's what I see on screen."):
        speak("I couldn't find any readable text on screen.")


# ---- registered commands, in original priority order ----

@command(["read whatsapp", "whatsapp messages", "new messages"])
def handle_read_whatsapp(command_text):
    read_whatsapp()


@command(lambda cmd: cmd.startswith("launch pdf") or cmd.startswith("open pdf"))
def handle_launch_pdf(command_text):
    hint = re.sub(r"^(launch|open) pdf", "", command_text).strip()
    pdf_reader.launch_pdf_file(hint or None)


@command(lambda cmd: cmd.startswith("read pdf"))
def handle_read_pdf(command_text):
    hint = command_text[len("read pdf"):].strip()
    if pdf_reader.open_pdf(hint or None):
        pdf_reader.read_pdf_page()


@command("read page")
def handle_read_page(command_text):
    pdf_reader.read_pdf_page(extract_number(command_text))


# "go to page X" is checked BEFORE the plain "next page"/"previous page"
# below on purpose - see the module-level note in the original file.
@command(["go to page", "goto page", "jump to page"])
def handle_go_to_page(command_text):
    handle_go_to_page_action(extract_number(command_text))


@command(["next page", "next slide"])
def handle_next_page(command_text):
    handle_next_page_action()


@command(["previous page", "last page", "go back a page", "previous slide"])
def handle_previous_page(command_text):
    handle_previous_page_action()


@command(["read screen", "what's on my screen", "whats on my screen", "read the screen"])
def handle_read_screen(command_text):
    read_screen()
