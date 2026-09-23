"""
COMMANDS: click on screen (OCR)

  "click search bar" / "find search bar"  -> checked FIRST: a dedicated
                                              search-box locator (see
                                              nexon.ocr.find_search_bar),
                                              since it would otherwise be
                                              swallowed by the generic
                                              "click " handler below
  "double click <text>"                   -> checked before "click " so
                                              it's never swallowed by it
  "click <text>"                          -> clicks the center of the
                                              best-matching line

Only works on visible, OCR-readable text - a labeled button, a video
title, a menu item. Can't click a bare icon or unlabeled thumbnail.
"""

from .. import ocr
from ..registry import command
from ..tts import speak


@command(["click search bar", "click the search bar", "click search box", "click the search box", "find search bar"])
def handle_click_search_bar(command_text):
    if ocr.click_search_bar():
        speak("Clicked the search bar.")
    else:
        speak("I couldn't find a search bar on screen.")


@command(lambda cmd: cmd.startswith("double click "))
def handle_double_click(command_text):
    target = command_text[len("double click "):].strip()
    ocr.click_on_screen(target, double=True, speak=speak)


@command(lambda cmd: cmd.startswith("click "))
def handle_click(command_text):
    target = command_text[len("click "):].strip()
    ocr.click_on_screen(target, speak=speak)
