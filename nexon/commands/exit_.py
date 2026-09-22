"""
COMMANDS: exit

  "shutdown assistant" / "exit" / "quit" / "goodbye"  -> stop nexon

Kept last in the import order (see commands/__init__.py) since these are
broad, generic words that should only fire once nothing more specific
has already claimed the command.
"""

from ..registry import command
from ..tts import speak


@command(["shutdown assistant", "exit", "quit", "goodbye"])
def handle_exit(command_text):
    speak("Goodbye.")
    return False
