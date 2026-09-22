"""
COMMANDS: brightness

  "set brightness to 50" / "brightness to 50"   -> exact percentage
  "brightness up" / "increase brightness"       -> step up
  "brightness down" / "decrease brightness"     -> step down
"""

import screen_brightness_control as sbc

from ..config import BRIGHTNESS_STEP
from ..helpers import extract_number
from ..registry import command
from ..tts import speak


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


# ---- registered commands ----

@command(["set brightness", "brightness to"])
def handle_set_brightness(command_text):
    level = extract_number(command_text)
    if level is not None:
        set_brightness(level)
        speak(f"Brightness set to {level}")
    else:
        speak("I didn't catch the brightness level.")


@command(["brightness up", "increase brightness"])
def handle_brightness_up(command_text):
    brightness_up()
    speak("Brightness up", wait=False)


@command(["brightness down", "decrease brightness"])
def handle_brightness_down(command_text):
    brightness_down()
    speak("Brightness down", wait=False)
