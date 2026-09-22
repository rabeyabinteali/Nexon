"""
COMMANDS: scrolling

  "scroll up [N]"    -> positive pyautogui.scroll()
  "scroll down [N]"  -> negative pyautogui.scroll()

An optional trailing number lets you say "scroll down 3".
"""

import pyautogui

from ..config import SCROLL_STEP
from ..helpers import extract_number
from ..registry import command
from ..tts import speak


def scroll_up(amount=SCROLL_STEP):
    amount = 300
    pyautogui.scroll(amount)


def scroll_down(amount=SCROLL_STEP):
    amount = 300
    pyautogui.scroll(-amount)


@command("scroll up")
def handle_scroll_up(command_text):
    amount = extract_number(command_text) or SCROLL_STEP
    scroll_up(amount)
    speak("Scrolled up")


@command("scroll down")
def handle_scroll_down(command_text):
    amount = extract_number(command_text) or SCROLL_STEP
    scroll_down(amount)
    speak("Scrolled down")
