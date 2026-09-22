"""
nexon.dispatcher
----------------
process_command() is the one function main.py calls with whatever text
was heard. It doesn't know about volume, browsers, or PDFs - it just
imports nexon.commands (which, as a side effect of being imported,
registers every command from every feature module) and hands the text
to the registry.
"""

from .tts import speak
from . import registry
from . import commands  # noqa: F401  (import registers every @command handler)


def _unknown(command_text):
    speak("I don't know that command yet.")
    return True


def process_command(command_text):
    if not command_text:
        return True
    return registry.dispatch(command_text, fallback=_unknown)
