"""
nexon.registry
--------------
The plugin mechanism. Each command module (nexon/commands/*.py) declares
its own trigger phrases with the @command decorator, right next to the
function that handles them. The dispatcher never lists commands by
name - it just walks every handler that has ever been registered, in
the order the feature modules were imported, and runs the first one
whose trigger matches.

This is what makes "add a command to webbrowser.py and it's live
everywhere" true: nothing outside commands/browser.py needs to know the
new phrase exists. The only thing that can still require a second edit
is import ORDER in commands/__init__.py, and only when a brand new
phrase could be mistaken for another feature's phrase (e.g. "open pdf x"
vs. the generic "open <site>") - see the comments there.
"""

_handlers = []  # list of (predicate, func, label), in registration order


def command(match):
    """
    Decorator that registers `func` as a command handler.

    `match` can be:
      - a string: matched with `match in command_text`
      - a list/tuple of strings: matches if ANY is a substring
      - a callable: predicate(command_text) -> bool, for anything
        fancier (startswith, regex, "ends with", combined conditions...)

    The handler is called as handler(command_text) and should return:
      - True, or nothing at all (None), to keep nexon running - the
        normal case
      - False to signal that the main loop should shut down (used only
        by the exit command)
    """
    predicate = _as_predicate(match)

    def decorator(func):
        _handlers.append((predicate, func, func.__name__))
        return func

    return decorator

def _as_predicate(match):
    if callable(match):
        return match
    phrases = [match] if isinstance(match, str) else list(match)
    return lambda cmd: any(phrase in cmd for phrase in phrases)


def dispatch(command_text, fallback):
    """
    Run the first registered handler whose match fires, in registration
    order. If none match, call fallback(command_text) instead.
    """
    for predicate, func, _label in _handlers:
        if predicate(command_text):
            result = func(command_text)
            return True if result is None else result
    return fallback(command_text)


def registered_count():
    """Mostly useful for a sanity-check print at startup / in tests."""
    return len(_handlers)
