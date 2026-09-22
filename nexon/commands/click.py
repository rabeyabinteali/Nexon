"""
COMMANDS: click on screen (OCR)

  "double click <text>"  -> checked FIRST so it's never swallowed by "click "
  "click <text>"         -> clicks the center of the best-matching line

Only works on visible, OCR-readable text - a labeled button, a video
title, a menu item. Can't click a bare icon or unlabeled thumbnail.
"""

from .. import ocr
from ..registry import command
from ..tts import speak


@command(lambda cmd: cmd.startswith("double click "))
def handle_double_click(command_text):
    target = command_text[len("double click "):].strip()
    ocr.click_on_screen(target, double=True, speak=speak)


@command(lambda cmd: cmd.startswith("click "))
def handle_click(command_text):
    target = command_text[len("click "):].strip()
    ocr.click_on_screen(target, speak=speak)
