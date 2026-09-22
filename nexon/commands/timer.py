"""
COMMANDS: countdown timer & stopwatch

  "set a timer for 5 minutes" / "timer for 90 seconds"  -> countdown timer
  "cancel timer" / "cancel timers" / "stop the timer"    -> cancel all
  "start timer" / "start stopwatch"                      -> stopwatch
  "stop timer" / "stop stopwatch"                         -> stopwatch

Add a new phrase (or a whole new duration-parsing trick) here and it's
picked up automatically - nothing else needs to change.
"""

import re
import threading
import time

from ..config import HAS_WINSOUND
from ..registry import command
from ..tts import speak

if HAS_WINSOUND:
    import winsound

_stopwatch_start = None
_active_timers = []


def _format_duration(seconds):
    """Turn a number of seconds into a spoken-friendly string like '2 minutes, 5 seconds'."""
    seconds = int(round(seconds))
    hrs, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if hrs:
        parts.append(f"{hrs} hour{'s' if hrs != 1 else ''}")
    if mins:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return ", ".join(parts)


def parse_duration_command(command_text):
    """
    Pull a duration out of a command like 'timer for 2 minutes' or
    'set a timer for 90 seconds'. Returns (seconds, spoken_label) or
    (None, None) if nothing was found.
    """
    match = re.search(r"(\d+)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)", command_text)
    if not match:
        return None, None

    value = int(match.group(1))
    unit = match.group(2)

    if unit.startswith("h"):
        seconds, unit_label = value * 3600, "hour" if value == 1 else "hours"
    elif unit.startswith("m"):
        seconds, unit_label = value * 60, "minute" if value == 1 else "minutes"
    else:
        seconds, unit_label = value, "second" if value == 1 else "seconds"

    return seconds, f"{value} {unit_label}"


def _ring_alarm(label):
    """Beep a few times (if possible) then announce the timer is done."""
    if HAS_WINSOUND:
        try:
            for _ in range(6):
                winsound.Beep(1000, 400)
                time.sleep(0.15)
        except Exception as e:
            print(f"Alarm beep error: {e}")
    speak(f"Time's up! Your {label} timer is done.")


def start_timer(seconds, label):
    """Start a countdown timer that rings after `seconds`, without blocking nexon."""
    def _on_ring():
        _ring_alarm(label)
        if timer_obj in _active_timers:
            _active_timers.remove(timer_obj)

    timer_obj = threading.Timer(seconds, _on_ring)
    timer_obj.daemon = True
    timer_obj.start()
    _active_timers.append(timer_obj)
    speak(f"Timer set for {label}.")


def cancel_all_timers():
    global _active_timers
    if not _active_timers:
        speak("No timers are running.")
        return
    for t in _active_timers:
        t.cancel()
    _active_timers = []
    speak("Timers cancelled.")


def start_stopwatch():
    global _stopwatch_start
    _stopwatch_start = time.time()
    speak("Stopwatch started.")


def stop_stopwatch():
    global _stopwatch_start
    if _stopwatch_start is None:
        speak("The stopwatch isn't running.")
        return
    elapsed = time.time() - _stopwatch_start
    _stopwatch_start = None
    speak(f"Stopped. Elapsed time: {_format_duration(elapsed)}.")


# ---- registered commands, in original priority order ----
# ("timer for" is checked before the stopwatch's "start timer" so
# "start a timer for 5 minutes" is never swallowed by the stopwatch.)

@command(lambda cmd: "timer for" in cmd or re.search(r"set (a |an )?timer", cmd))
def handle_set_timer(command_text):
    seconds, label = parse_duration_command(command_text)
    if seconds:
        start_timer(seconds, label)
    else:
        speak("How long should I set the timer for?")


@command(["cancel timer", "cancel timers", "stop the timer"])
def handle_cancel_timer(command_text):
    cancel_all_timers()


@command(["start timer", "start stopwatch"])
def handle_start_stopwatch(command_text):
    start_stopwatch()


@command(["stop timer", "stop stopwatch"])
def handle_stop_stopwatch(command_text):
    stop_stopwatch()
