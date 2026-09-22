"""
COMMANDS: misc system

  "screenshot" / "take a screenshot"  -> saves a numbered screenshot
"""

import os

import pyautogui

from ..config import SCREENSHOT_DIR
from ..registry import command
from ..tts import speak

_screenshot_counter = 1


def take_screenshot():
    global _screenshot_counter
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, f"Screenshot{_screenshot_counter}.png")
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
    print(f"Screenshot saved to: {path}")
    _screenshot_counter += 1
    speak("Screenshot saved.")


@command(["screenshot", "take a screenshot"])
def handle_screenshot(command_text):
    take_screenshot()
