"""
nexon.pdf_reader
----------------
Locating PDFs by (fuzzy, spoken) filename, opening them, and reading
pages aloud with position tracking. Used only by
nexon.commands.screen_reading, but kept as its own module since it's a
self-contained chunk of logic.
"""

import difflib
import os
import re
import threading
import time

import pygetwindow as gw
import pymupdf
import pytesseract
from PIL import Image

from . import config
from .helpers import normalize_for_match
from .tts import speak

# Tracks the currently "open" PDF for read screen / next page / previous page
_pdf_state = {"path": None, "doc": None, "page": 0}

# Cached list of (path, normalized_name, name_words) for every PDF under
# PDF_SEARCH_DIRS. Walking those folders is the slow part of finding a
# PDF, so it's done once (in the background at startup) and reused.
_pdf_index = []
_pdf_index_time = 0.0
_pdf_index_lock = threading.Lock()
_PDF_SKIP_DIRS = {"node_modules", "__pycache__", "venv", "env", "site-packages"}


def has_open_pdf():
    return _pdf_state["doc"] is not None


def _build_pdf_index_locked():
    """Rescan PDF_SEARCH_DIRS. Caller must hold _pdf_index_lock."""
    global _pdf_index, _pdf_index_time
    entries = []
    for folder in config.PDF_SEARCH_DIRS:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            # Skip hidden folders and huge dependency folders.
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d.lower() not in _PDF_SKIP_DIRS]
            for name in files:
                if name.startswith(".") or not name.lower().endswith(".pdf"):
                    continue
                base_norm = normalize_for_match(os.path.splitext(name)[0])
                if base_norm:
                    entries.append((os.path.join(root, name), base_norm, base_norm.split()))
    _pdf_index = entries
    _pdf_index_time = time.time()


def get_pdf_index(max_age=config.PDF_INDEX_MAX_AGE):
    """Return the cached PDF list, rescanning if it's missing or older than max_age seconds."""
    with _pdf_index_lock:
        if _pdf_index_time == 0.0 or time.time() - _pdf_index_time > max_age:
            _build_pdf_index_locked()
        return _pdf_index


def build_pdf_index_in_background():
    """Call at startup so the first 'read pdf' doesn't have to wait for a folder scan."""
    threading.Thread(target=get_pdf_index, daemon=True).start()


def _match_pdf(hint_norm, hint_words, index):
    best_path = None
    best_rank = None

    for path, base_norm, base_words in index:
        if hint_norm in base_norm:
            rank = (0, 0)
        elif all(w in base_words for w in hint_words):
            rank = (1, 0)
        else:
            similarity = difflib.SequenceMatcher(None, hint_norm, base_norm).ratio()
            if similarity < config.FUZZY_MATCH_THRESHOLD:
                continue
            rank = (2, -similarity)

        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_path = path

    return best_path


def _find_pdf_file(hint):
    """
    Search the cached PDF index for a PDF matching `hint`. Matching is
    fuzzy on purpose, since spoken filenames rarely line up exactly with
    how a file is actually named on disk:

      1. Exact normalized substring match (best).
      2. All hint words present somewhere in the filename, any order.
      3. Fallback: similarity-ratio fuzzy match, accepted only above
         FUZZY_MATCH_THRESHOLD.

    Returns the single best matching path, or None. If nothing matches
    and the cached index is more than PDF_INDEX_MIN_REFRESH seconds old,
    the folders are rescanned once in case the file is new.
    """
    hint_norm = normalize_for_match(hint)
    if not hint_norm:
        return None
    hint_words = hint_norm.split()

    path = _match_pdf(hint_norm, hint_words, get_pdf_index())
    if path is None and time.time() - _pdf_index_time > config.PDF_INDEX_MIN_REFRESH:
        path = _match_pdf(hint_norm, hint_words, get_pdf_index(max_age=config.PDF_INDEX_MIN_REFRESH))
    return path


def get_active_window_title():
    try:
        win = gw.getActiveWindow()
        return win.title if win else ""
    except Exception:
        return ""


def _locate_pdf(name_hint=None):
    """
    Figure out which PDF file to open: use a spoken filename hint if
    given, otherwise try to guess from the active window's title bar
    (most PDF viewers put the filename there).
    """
    if name_hint:
        found = _find_pdf_file(name_hint)
        if found:
            return found

    title = get_active_window_title()
    match = re.search(r"([\w,\s\-\_\(\)]+\.pdf)", title, re.IGNORECASE)
    if match:
        return _find_pdf_file(os.path.splitext(match.group(1))[0])

    return None


def open_pdf(name_hint=None):
    """Locate and open a PDF, resetting page position to the start."""
    global _pdf_state

    path = _locate_pdf(name_hint)
    if not path:
        speak("I couldn't find that PDF. Make sure it's in Desktop, Documents, or Downloads.")
        return False

    try:
        doc = pymupdf.open(path)
    except Exception as e:
        print(f"PDF open error: {e}")
        speak("I couldn't open that PDF.")
        return False

    _pdf_state = {"path": path, "doc": doc, "page": 0}
    speak(f"Opened {os.path.basename(path)}. {doc.page_count} pages.")
    return True


def launch_pdf_file(name_hint=None):
    """
    Find a PDF by (partial, fuzzy) filename and open it in the system's
    default PDF viewer - like double-clicking it in Explorer. Unlike
    open_pdf()/read_pdf_page(), this does NOT load the file into nexon's
    own reader state. Windows only (os.startfile).
    """
    path = _locate_pdf(name_hint)
    if not path:
        speak("I couldn't find that PDF. Make sure it's in Desktop, Documents, or Downloads.")
        return False

    try:
        os.startfile(path)
    except AttributeError:
        speak("Launching files in their default viewer only works on Windows.")
        return False
    except Exception as e:
        print(f"PDF launch error: {e}")
        speak("I found the file but couldn't open it.")
        return False

    speak(f"Opening {os.path.basename(path)}.")
    return True


def _ocr_pdf_page(page):
    """OCR fallback for a PDF page with no extractable text (e.g. a scan)."""
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        print(f"OCR error: {e}")
        return ""


def read_pdf_page(page_number=None):
    """Read the current (or given) page of the currently open PDF aloud."""
    from .helpers import speak_long_text  # local import: helpers imports tts, not this module

    doc = _pdf_state["doc"]
    if doc is None:
        speak("No PDF is open. Say 'read screen' with a PDF focused, or 'read pdf' and the filename.")
        return

    index = page_number - 1 if page_number is not None else _pdf_state["page"]

    if index < 0 or index >= doc.page_count:
        speak("That page doesn't exist.")
        return

    _pdf_state["page"] = index
    text = doc[index].get_text().strip()

    if not text:
        text = _ocr_pdf_page(doc[index])

    if not text:
        speak(f"Page {index + 1} doesn't seem to have any readable text.")
        return

    speak_long_text(text, prefix=f"Page {index + 1} of {doc.page_count}.")


def next_pdf_page():
    if _pdf_state["doc"] is None:
        speak("No PDF is open.")
        return
    _pdf_state["page"] += 1
    read_pdf_page()


def previous_pdf_page():
    if _pdf_state["doc"] is None:
        speak("No PDF is open.")
        return
    _pdf_state["page"] = max(0, _pdf_state["page"] - 1)
    read_pdf_page()
