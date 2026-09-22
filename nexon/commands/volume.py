"""
COMMANDS: volume

  "set volume to 50" / "volume to 50"   -> exact percentage (pycaw, Windows only)
  "volume up" / "increase volume"       -> step up
  "volume down" / "decrease volume"     -> step down
  "mute"                                -> mute

Exact volume control (pycaw) is Windows-only. For cross-platform
support, swap set_volume() for an osascript (macOS) or pactl/amixer
(Linux) call.
"""

from ctypes import cast, POINTER

import pyautogui
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from ..config import VOLUME_STEP
from ..helpers import extract_number
from ..registry import command
from ..tts import speak


def volume_up():
    pyautogui.press("volumeup", presses=VOLUME_STEP)


def volume_down():
    pyautogui.press("volumedown", presses=VOLUME_STEP)


def mute():
    pyautogui.press("volumemute")


def set_volume(level):
    """Set system volume to an exact percentage (0-100). Windows only (pycaw)."""
    level = max(0, min(100, level))
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100, None)
    except Exception as e:
        print(f"Volume error: {e}")


# ---- registered commands ----
# ("set volume"/"volume to" is a distinct phrase from "volume up"/"volume
# down"/"mute" below, so which is checked first doesn't matter here.)

@command(["set volume", "volume to"])
def handle_set_volume(command_text):
    level = extract_number(command_text)
    if level is not None:
        set_volume(level)
        speak(f"Volume set to {level}")
    else:
        speak("I didn't catch the volume level.")


@command(["volume up", "increase volume"])
def handle_volume_up(command_text):
    volume_up()
    speak("Volume up", wait=False)


@command(["volume down", "decrease volume"])
def handle_volume_down(command_text):
    volume_down()
    speak("Volume down", wait=False)


@command("mute")
def handle_mute(command_text):
    mute()
    speak("Muted", wait=False)
