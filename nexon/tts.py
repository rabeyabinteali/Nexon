"""
nexon.tts
---------
Text-to-speech, on a single dedicated thread.

pyttsx3 (and the SAPI5/COM engine it wraps on Windows) is not safe to
use from multiple threads. Several call sites need to speak from a
background thread - skip_ad()'s polling worker, countdown timers ringing
via threading.Timer - and if one of those overlaps with the main loop
calling speak() for the next command, the engine can end up wedged (a
COM error, or pyttsx3's "run loop already started"), after which every
subsequent speak() call can hang or silently do nothing.

The fix: create and use the pyttsx3 engine on exactly one thread, ever.
Every other thread just drops text into a queue for that thread to speak.
"""

import queue
import threading
import time

import pyttsx3

_tts_queue = queue.Queue()

# True while nexon is actually speaking. The background listener checks
# this and drops whatever it just heard instead of treating it as a
# command - otherwise, with the mic always on, nexon's own voice coming
# out of the speakers can get picked back up and misheard as you talking
# to it.
is_speaking = threading.Event()


def _tts_worker():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass  # not on Windows / pywin32 unavailable - fine for other drivers

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)
    engine.setProperty("volume", 1.0)

    while True:
        text = _tts_queue.get()
        try:
            if text is None:
                break
            print(f"nexon: {text}")
            is_speaking.set()
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            # Small grace period: audio lingering in the air / speaker
            # buffers can still reach the mic for a moment after
            # runAndWait() returns.
            time.sleep(0.3)
            is_speaking.clear()
            _tts_queue.task_done()


_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


def speak(text, wait=True):
    """
    Speak text aloud. Safe to call from any thread - this only ever
    enqueues the text; the actual pyttsx3 engine is owned and driven
    entirely by _tts_worker on its own thread.

    wait=True (the default) blocks until everything currently queued has
    been spoken. Pass wait=False for a fire-and-forget announcement.
    """
    _tts_queue.put(text)
    if wait:
        _tts_queue.join()
