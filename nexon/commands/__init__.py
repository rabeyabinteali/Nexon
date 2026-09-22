"""
nexon.commands
--------------
Every module imported below registers its own commands (via
@nexon.registry.command) purely as a side effect of being imported.
That's the whole plugin system: to add a brand-new command family,
create commands/your_feature.py using the existing files as a template,
add one import line here, and it's part of nexon.

TO ADD A COMMAND TO AN EXISTING FEATURE (e.g. a new web browser command):
just edit that feature's file (e.g. browser.py) and add a new
@command(...)-decorated function. Nothing here needs to change.

Import order below only matters for the two cases noted inline, where
one feature's trigger phrase is a superset of another's and the more
specific one must be tried first.
"""

from . import timer
from . import volume
from . import brightness
from . import screen_reading   # must precede `browser`: "open/launch pdf ..."
                                # needs to be claimed before browser's generic "open <site>"
from . import scrolling
from . import click
from . import files
from . import dictation
from . import browser          # must precede `media`: "play <song> [on youtube]"
                                # needs to be claimed before media's generic "pause"/"play"
from . import media
from . import system
from . import exit_             # keep last (before the registry's built-in fallback):
                                 # catches broad words like "exit"/"quit"/"goodbye"

__all__ = [
    "timer", "volume", "brightness", "screen_reading", "scrolling",
    "click", "files", "dictation", "browser", "media", "system", "exit_",
]
