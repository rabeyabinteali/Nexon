"""
nexon.speech
------------
Everything about turning audio into command text: the always-on
background listener, local (faster-whisper) and online (Google)
recognition, and the blocking listen_raw() used for dictation.

ALWAYS-ON BACKGROUND LISTENING
-------------------------------
The old approach called a blocking listen() in a loop: open the mic,
wait up to PHRASE_TIME_LIMIT seconds of audio, close the mic, THEN send
it off to Google for recognition, and only after all of that loop back
around and open the mic again. Two things fell out of that:

  1. PHRASE_TIME_LIMIT was a hard ceiling on the mic capture itself, so
     any command that took longer to say than that limit got cut off
     mid-sentence.
  2. The mic was only ever open DURING that fixed window, so anything
     you said in the gap while it was closed was simply never captured.

SpeechRecognition's listen_in_background() fixes both: it keeps exactly
one mic stream open continuously on its own thread for as long as the
program runs, and calls a callback for every phrase it detects (a phrase
ends on its own after PAUSE_THRESHOLD seconds of silence, not a fixed
clock). PHRASE_TIME_LIMIT is only a safety ceiling now, not the
listening window. Recognized text is dropped into a queue; the main loop
just pulls from that queue, so there's never a gap where nexon isn't
listening.
"""

import queue
import re
import socket
import threading
import time

import speech_recognition as sr

from . import config
from .tts import is_speaking

recognizer = sr.Recognizer()
recognizer.pause_threshold = config.PAUSE_THRESHOLD
# Without this, recognize_google() can wait forever on a bad connection.
recognizer.operation_timeout = 10

_heard_queue = queue.Queue()
_audio_queue = queue.Queue()

# Holds the stop_listening() callable SpeechRecognition gives back, so
# pause/resume can stop and restart the one background stream. Only ever
# one mic stream should be open at a time - anything that needs the mic
# directly (like listen_raw()) must pause this first.
_stop_listening = None

_mic_sample_rate = config.MIC_SAMPLE_RATE
_mic_rate_verified = False

# --------------------------------------------------
# LOCAL SPEECH RECOGNITION (faster-whisper)
# --------------------------------------------------

_whisper_model = None
_whisper_failed = False
_whisper_lock = threading.Lock()


def _get_whisper():
    """
    Load the local model once (first call downloads it). Returns the
    model, or None if it isn't available - in which case callers use
    Google.
    """
    global _whisper_model, _whisper_failed
    if _whisper_model is not None or _whisper_failed:
        return _whisper_model

    with _whisper_lock:
        if _whisper_model is not None or _whisper_failed:
            return _whisper_model
        try:
            import numpy as np
            from faster_whisper import WhisperModel

            print(f"Loading local speech model '{config.WHISPER_MODEL}' (first run downloads it)...")
            model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
            # Warm-up: the very first inference is always slower.
            list(model.transcribe(np.zeros(16000, dtype="float32"), language="en")[0])
            _whisper_model = model
            print("Local speech model ready.")
        except Exception as e:
            print(f"Local speech model unavailable ({e}).")
            print("Using Google recognition instead. For faster recognition: pip install faster-whisper")
            _whisper_failed = True
    return _whisper_model


def preload_whisper():
    """
    Called at startup so 'nexon is ready' is actually true. Loaded for
    both "whisper" and "auto" modes, since "auto" can need the local
    model at any moment (as soon as the network looks slow/down) and
    loading it for the first time mid-conversation would stall nexon
    right when the network just failed.
    """
    if config.RECOGNITION_ENGINE in ("whisper", "auto"):
        _get_whisper()


# --------------------------------------------------
# ENGINE SELECTION (RECOGNITION_ENGINE == "auto")
# --------------------------------------------------
#
# "auto" tries to use Google whenever the network looks fast enough
# (more accurate, no local model needed) and falls back to local
# faster-whisper whenever it isn't. Two different signals can trigger
# the fallback:
#
#   1. A quick, cheap reachability check (_network_reachable) BEFORE
#      even trying Google - catches "no network at all" without paying
#      Google's own (much longer) connection timeout first.
#   2. The actual recognize_google() call itself being slow or failing
#      - catches "network is up but bad" (e.g. high latency, packet
#      loss), which the quick check above can't see.
#
# Either signal marks the network "bad" for NETWORK_RECHECK_INTERVAL
# seconds, during which every call goes straight to local recognition
# without re-testing the network on every single phrase. After that
# window, nexon quietly tries Google again.

_network_bad_until = 0.0


def _network_reachable():
    """Cheap, fast check: can we open a socket at all right now?"""
    try:
        with socket.create_connection(config.NETWORK_CHECK_HOST, timeout=config.NETWORK_CHECK_TIMEOUT):
            return True
    except OSError:
        return False


def _mark_network_bad(reason):
    global _network_bad_until
    _network_bad_until = time.time() + config.NETWORK_RECHECK_INTERVAL
    if config.DEBUG_TIMING:
        print(f"[network {reason} - using local recognition for {config.NETWORK_RECHECK_INTERVAL}s]")


def _select_engine():
    """Return 'google' or 'whisper' - which engine the NEXT call should use."""
    engine = config.RECOGNITION_ENGINE

    if engine == "google":
        return "google"

    if engine == "whisper":
        return "whisper" if _get_whisper() is not None else "google"

    # "auto"
    if time.time() < _network_bad_until:
        return "whisper" if _get_whisper() is not None else "google"

    if _network_reachable():
        return "google"

    _mark_network_bad("unreachable")
    return "whisper" if _get_whisper() is not None else "google"


def _use_local_engine():
    return _select_engine() == "whisper"


def _normalize_command_text(text):
    """
    Whisper adds capitals and punctuation ("nexon, next video."); the
    command matching in nexon.commands expects plain lowercase words
    like Google returned.
    """
    text = re.sub(r"[^\w\s]", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    for variant in config.WAKE_WORD_VARIANTS:
        text = re.sub(rf"\b{re.escape(variant)}\b", config.WAKE_WORD, text)
    return text


def _recognize_local(audio, use_prompt=True):
    """
    Transcribe an sr.AudioData clip on this PC. Returns the text with
    Whisper's own casing/punctuation ("" if nothing was said).
    """
    import numpy as np

    model = _get_whisper()
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    segments, _info = model.transcribe(
        samples,
        language="en",
        beam_size=1,                      # greedy decoding: fastest
        temperature=0.0,                  # no slow retry loop
        vad_filter=True,                  # skips silence/noise-only clips
        condition_on_previous_text=False,
        initial_prompt=config.WHISPER_PROMPT if use_prompt else None,
    )

    parts = []
    for seg in segments:
        # Drop segments Whisper itself thinks aren't really speech.
        if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
            continue
        parts.append(seg.text.strip())
    text = " ".join(p for p in parts if p).strip()

    # If Whisper just echoes the hint text back on a noisy clip, ignore it.
    if use_prompt and len(text.split()) >= 6:
        if _normalize_command_text(text) in _normalize_command_text(config.WHISPER_PROMPT):
            return ""
    return text


def _recognize_with_whisper_timed(audio):
    t0 = time.time()
    text = _normalize_command_text(_recognize_local(audio))
    if config.DEBUG_TIMING:
        secs = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
        print(f"[local {config.WHISPER_MODEL} | audio {secs:.1f}s | took {time.time() - t0:.2f}s]")
    return text


def _recognize_command(audio):
    """Audio -> plain lowercase command text ('' if nothing)."""
    engine = _select_engine()

    if engine == "whisper":
        return _recognize_with_whisper_timed(audio)

    if config.DEBUG_TIMING:
        # Measured separately so "encoding the audio" can be told apart
        # from "waiting on Google": network time is roughly (total - encode).
        secs = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
        t_enc = time.time()
        flac_kb = len(audio.get_flac_data()) / 1024
        enc = time.time() - t_enc

    t0 = time.time()
    try:
        text = recognizer.recognize_google(audio).lower().strip()
    except (sr.RequestError, OSError) as e:
        # Google itself failed to respond (not "understood nothing" -
        # that's sr.UnknownValueError, left to propagate as before). In
        # "auto" mode, treat this as a bad network: fall back to local
        # for this phrase (rather than losing it) and for a while after.
        if config.RECOGNITION_ENGINE == "auto" and _get_whisper() is not None:
            _mark_network_bad("request failed")
            return _recognize_with_whisper_timed(audio)
        raise

    total = time.time() - t0
    if config.DEBUG_TIMING:
        print(f"[google | audio {secs:.1f}s, {flac_kb:.0f}KB upload | "
              f"encode {enc:.2f}s | recognize total {total:.2f}s | "
              f"network ~{max(total - enc, 0):.2f}s]")

    if config.RECOGNITION_ENGINE == "auto" and total > config.GOOGLE_SLOW_THRESHOLD:
        _mark_network_bad(f"slow ({total:.1f}s)")

    return text


def _background_listen_callback(recognizer_instance, audio):
    """
    Runs on SpeechRecognition's listener thread for every captured
    phrase. It must return FAST: while this callback runs, the mic isn't
    being read. So it only hands the audio to _recognition_worker, which
    does the slow recognition call on its own thread.
    """
    if is_speaking.is_set():
        return
    _audio_queue.put(audio)


def _recognition_worker():
    """Turns queued audio into text (one phrase at a time, in order)."""
    while True:
        audio = _audio_queue.get()
        if audio is None:
            break

        if is_speaking.is_set():
            continue

        try:
            text = _recognize_command(audio)
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            print(f"Speech recognition error: {e}")
            continue
        except Exception as e:  # e.g. socket timeout
            print(f"Speech recognition error: {e}")
            continue

        if text and not is_speaking.is_set():
            print(f"You: {text}")
            _heard_queue.put(text)


_recognition_thread = threading.Thread(target=_recognition_worker, daemon=True)
_recognition_thread.start()


def _make_microphone():
    """sr.Microphone at MIC_SAMPLE_RATE, falling back to the mic's default rate if unsupported."""
    global _mic_sample_rate, _mic_rate_verified
    if _mic_sample_rate is not None and not _mic_rate_verified:
        try:
            with sr.Microphone(sample_rate=_mic_sample_rate):
                pass
            _mic_rate_verified = True
        except Exception as e:
            print(f"Mic can't do {_mic_sample_rate} Hz ({e}); using its default rate instead.")
            _mic_sample_rate = None
    return sr.Microphone(sample_rate=_mic_sample_rate)


def start_background_listening():
    """
    Calibrates for ambient noise once, then starts the persistent
    background listener. Returns the stop_listening() callable that
    SpeechRecognition gives back, so main() can shut it down cleanly.
    """
    global _stop_listening

    mic = _make_microphone()

    with mic as source:
        print("Calibrating microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    # Lock the energy threshold in place after that one calibration
    # instead of letting it keep auto-adjusting for the rest of the
    # session - a long-running listener left on dynamic adjustment can
    # drift upward (e.g. a fridge humming) until it starts cutting real
    # speech short.
    recognizer.dynamic_energy_threshold = False

    _stop_listening = recognizer.listen_in_background(
        mic,
        _background_listen_callback,
        phrase_time_limit=config.PHRASE_TIME_LIMIT
    )
    return _stop_listening


def pause_background_listening():
    """
    Stops the always-on listener so a call site that needs the mic
    directly (e.g. listen_raw() for dictation) can open its own stream
    without fighting the background one for the same device. Always
    pair with resume_background_listening().
    """
    global _stop_listening
    if _stop_listening is not None:
        _stop_listening(wait_for_stop=True)
        _stop_listening = None


def resume_background_listening():
    """Restarts the always-on listener after pause_background_listening()."""
    if _stop_listening is None:
        start_background_listening()


def get_heard(timeout=None):
    """
    Pull the next recognized phrase off the background listener's queue.
    Returns "" if nothing came in within `timeout` seconds (or
    immediately, if timeout is None/0 and the queue is empty).
    """
    try:
        return _heard_queue.get(timeout=timeout)
    except queue.Empty:
        return ""


def listen_raw():
    """
    Blocking single-shot listen that preserves original casing/
    punctuation from the recognizer instead of lowercasing - used for
    dictating actual message text. Pauses the always-on background
    listener for the duration of the call and resumes it afterward,
    since only one mic stream can be open at once.
    """
    pause_background_listening()
    recognizer.pause_threshold = config.DICTATION_PAUSE_THRESHOLD
    try:
        with _make_microphone() as source:
            print("Listening...")
            try:
                audio = recognizer.listen(
                    source,
                    timeout=config.COMMAND_TIMEOUT,
                    phrase_time_limit=config.DICTATION_PHRASE_TIME_LIMIT
                )
            except sr.WaitTimeoutError:
                return ""
    finally:
        recognizer.pause_threshold = config.PAUSE_THRESHOLD
        resume_background_listening()

    engine = _select_engine()
    try:
        if engine == "whisper":
            text = _recognize_local(audio, use_prompt=False)
        else:
            text = recognizer.recognize_google(audio)
        if not text.strip():
            return ""
        print(f"You (dictated): {text}")
        return text.strip()

    except sr.UnknownValueError:
        return ""

    except (sr.RequestError, OSError) as e:  # OSError covers socket timeouts
        print(f"Speech recognition error: {e}")
        if engine == "google" and config.RECOGNITION_ENGINE == "auto" and _get_whisper() is not None:
            _mark_network_bad("request failed")
            try:
                return _recognize_local(audio, use_prompt=False).strip()
            except Exception as e2:
                print(f"Local fallback also failed: {e2}")
        return ""
