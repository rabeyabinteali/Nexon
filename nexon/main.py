"""
nexon.main
----------
The wake-word state machine and the run loop. This is the only place
that knows about "awake mode" - once a phrase is handed to
process_command(), the wake word has already been stripped off.
"""

import os

import keyboard

from . import config
from . import pdf_reader
from . import speech
from .dispatcher import process_command
from .tts import speak

_stay_awake = False


def kill_switch():
    print("nexon kill switch activated!")
    os._exit(0)


def _register_kill_switch():
    keyboard.add_hotkey("ctrl+alt+j", kill_switch)


def main():
    global _stay_awake

    _register_kill_switch()

    print("--------------------------------")
    print(" nexon voice assistant")
    print("--------------------------------")
    print(f"Wake word: {config.WAKE_WORD}")
    print("Say 'nexon' to activate.")
    print("Say 'nexon awake' to stop needing the wake word each time.")
    print("Say 'sleep' (while awake) or 'nexon sleep' to go back to normal.")
    print("Say 'shutdown assistant' to quit.")
    print()

    # Load the local speech model first (a few seconds; the first run also
    # downloads it), so "nexon is ready" is actually true.
    speech.preload_whisper()

    # Starts one continuously-open mic stream on its own background
    # thread - no gap where nexon isn't listening.
    stop_listening = speech.start_background_listening()

    # Build the PDF filename index in the background so the first
    # "read pdf" doesn't have to wait for a folder scan.
    pdf_reader.build_pdf_index_in_background()

    speak("nexon is ready.")

    running = True

    try:
        while running:

            # Pull the next recognized phrase off the queue. A short
            # timeout just keeps this loop responsive (e.g. to Ctrl+C);
            # the mic itself is always listening regardless of this.
            heard = speech.get_heard(timeout=0.2)

            if not heard:
                continue

            # ------------------------------------------
            # STAY-AWAKE MODE: no wake word needed. Every
            # heard phrase is tried directly as a command.
            # ------------------------------------------

            if _stay_awake:

                # If old habits kick in and "nexon" still gets said, strip it
                # off so e.g. "nexon next video" still works while awake.
                spoken = heard.split(config.WAKE_WORD, 1)[1].strip() if config.WAKE_WORD in heard else heard

                if not spoken:
                    continue

                if any(phrase in spoken for phrase in config.SLEEP_PHRASES):
                    _stay_awake = False
                    speak("Going back to sleep. Say nexon to wake me up.")
                    continue

                running = process_command(spoken)
                continue

            # ------------------------------------------
            # NORMAL MODE: wake word required
            # ------------------------------------------

            if config.WAKE_WORD in heard:

                # If you said "nexon next video" we can use the rest immediately.
                cmd = heard.split(config.WAKE_WORD, 1)[1].strip()

                if not cmd:
                    speak("Yes?")
                    # Wait for the follow-up command to arrive on the
                    # queue - the mic never stopped listening in the
                    # meantime, so nothing said right after "Yes?" is lost.
                    cmd = speech.get_heard(timeout=config.COMMAND_TIMEOUT)

                if cmd and any(phrase in cmd for phrase in config.STAY_AWAKE_PHRASES):
                    _stay_awake = True
                    speak("I'll stay awake. Just say sleep, or nexon sleep, when you want me to stop.")
                elif cmd:
                    running = process_command(cmd)
    finally:
        stop_listening(wait_for_stop=False)


if __name__ == "__main__":
    main()
