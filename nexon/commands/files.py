"""
COMMANDS: file operations

  "clear/empty recycle bin"                       -> empty it, no confirmation
  "delete file" / "delete this file" / "delete"   -> Delete key
    (add "permanently"/"forever" to send Shift+Delete instead)

Both assume the file/item is already selected on screen - typically via
a prior "click <filename>" - and are just keystrokes sent to whichever
window has focus. Make sure File Explorer (with the right item
selected) is focused first.
"""

import pyautogui

from ..registry import command
from ..tts import speak


def delete_selected_file(permanent=False):
    """
    permanent=False (default) sends plain Delete, which moves the item to
    the Recycle Bin. permanent=True sends Shift+Delete, which skips the
    Recycle Bin entirely - Windows may pop up a confirmation dialog for
    this, which nexon does not click through for you.
    """
    if permanent:
        pyautogui.hotkey("shift", "delete")
        speak("Permanently deleted.")
    else:
        pyautogui.press("delete")
        speak("Moved to Recycle Bin.")


def clear_recycle_bin():
    """
    Empty the Windows Recycle Bin via a direct call into shell32
    (SHEmptyRecycleBinW) - no confirmation dialog, progress window, or
    sound. Windows only.
    """
    try:
        import ctypes
        SHERB_NOCONFIRMATION = 0x00000001
        SHERB_NOPROGRESSUI = 0x00000002
        SHERB_NOSOUND = 0x00000004
        flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        # 0 = success. -2147418113 (0x8000FFFF) shows up on some Windows
        # versions when the bin was already empty - not a real failure.
        if result not in (0, -2147418113):
            raise OSError(f"SHEmptyRecycleBinW returned {result}")
    except AttributeError:
        speak("Emptying the Recycle Bin only works on Windows.")
        return False
    except Exception as e:
        print(f"Recycle bin error: {e}")
        speak("I couldn't empty the Recycle Bin.")
        return False

    speak("Recycle Bin emptied.")
    return True


# ---- registered commands ----

@command([
    "clear recycle bin", "empty recycle bin", "clear the recycle bin",
    "empty the recycle bin", "empty the bin", "clear the bin",
    "empty bin", "clear bin",
])
def handle_clear_recycle_bin(command_text):
    clear_recycle_bin()


@command(lambda cmd: (
    "delete file" in cmd or "delete this file" in cmd
    or "delete the file" in cmd or cmd.strip() == "delete"
))
def handle_delete_file(command_text):
    permanent = "permanently" in command_text or "forever" in command_text
    delete_selected_file(permanent=permanent)
