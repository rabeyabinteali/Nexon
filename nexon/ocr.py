"""
nexon.ocr
---------
Screenshot -> OCR data -> "click this text" helpers. Shared by the click
commands (click.py) and the ad-skipping logic (media.py) - anything that
needs to find and click something visible but unlabeled-by-API on screen.
"""

import re
import time
import difflib

import pyautogui
import pytesseract

from . import config
from .helpers import normalize_for_match

if config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def shrink_for_ocr(image):
    """Downscale very wide screenshots so Tesseract runs faster. Returns (image, scale)."""
    w, h = image.size
    if w <= config.OCR_MAX_WIDTH:
        return image, 1.0
    scale = w / config.OCR_MAX_WIDTH
    return image.resize((config.OCR_MAX_WIDTH, round(h / scale))), scale


def ocr_data(image):
    """
    pytesseract.image_to_data() on a (possibly shrunk) image, with word
    positions scaled back to the original image's pixel coordinates.
    Returns the data dict, or None on failure.
    """
    small, scale = shrink_for_ocr(image)
    try:
        data = pytesseract.image_to_data(small, output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"OCR error: {e}")
        return None

    if scale != 1.0:
        for key in ("left", "top", "width", "height"):
            data[key] = [round(v * scale) for v in data[key]]
    return data


def find_clickable_text(target, data, screenshot_size=None):
    """
    Group OCR'd words into lines and find the best match for `target`.

    The returned point is scaled from the screenshot's pixel coordinates
    to PyAutoGUI's screen coordinates, which matters on Windows when
    display scaling/DPI settings differ between the two.
    """
    target_norm = normalize_for_match(target)
    if not target_norm:
        return None

    lines = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    best_idxs, best_rank = None, None
    for idxs in lines.values():
        line_norm = normalize_for_match(" ".join(data["text"][i] for i in idxs))
        if not line_norm:
            continue

        if target_norm in line_norm:
            rank = (0, 0)
        elif all(w in line_norm.split() for w in target_norm.split()):
            rank = (1, 0)
        else:
            sim = difflib.SequenceMatcher(None, target_norm, line_norm).ratio()
            if sim < config.FUZZY_MATCH_THRESHOLD:
                continue
            rank = (2, -sim)

        if best_rank is None or rank < best_rank:
            best_rank, best_idxs = rank, idxs

    if best_idxs is None:
        return None

    left = min(data["left"][i] for i in best_idxs)
    top = min(data["top"][i] for i in best_idxs)
    right = max(data["left"][i] + data["width"][i] for i in best_idxs)
    bottom = max(data["top"][i] + data["height"][i] for i in best_idxs)

    x = (left + right) / 2
    y = (top + bottom) / 2

    if screenshot_size:
        screen_w, screen_h = pyautogui.size()
        shot_w, shot_h = screenshot_size
        if shot_w and shot_h:
            x *= screen_w / shot_w
            y *= screen_h / shot_h

    return round(x), round(y)


def click_on_screen(target, double=False, speak=None):
    """
    OCR the screen, find text matching `target`, and click its center.
    Works for anything with visible text: a labeled button, a link, a
    video title, a menu item. Does NOT work on unlabeled icons/thumbnails
    since there's no OCR text there to match against.

    `speak` is injected (rather than imported) to avoid a circular import
    with nexon.tts; pass nexon.tts.speak.
    """
    target = (target or "").strip()
    if not target:
        speak("What should I click?")
        return False

    screenshot = pyautogui.screenshot()
    data = ocr_data(screenshot)
    if data is None:
        speak("I couldn't read the screen.")
        return False

    point = find_clickable_text(target, data, screenshot.size)
    if point is None:
        speak(f"I couldn't find anything on screen that says {target}.")
        return False

    # Move first so the target location is stable before clicking.
    pyautogui.moveTo(*point, duration=config.CLICK_MOVE_DURATION)

    if double:
        pyautogui.doubleClick(*point, interval=config.DOUBLE_CLICK_INTERVAL, duration=0)
        speak(f"Double clicked {target}.")
    else:
        pyautogui.click(*point)
        speak(f"Clicked {target}.")

    return True


def find_and_click_skip_button():
    """
    One OCR pass over the screen: look for a word containing 'skip'.
    Skip clicking if a digit sits close by on the same line (e.g.
    'Skip Ad in 4'), since that means the button isn't clickable yet.
    Only digits *near* the skip word count - Tesseract groups text into
    "lines" purely by vertical position, so an unrelated timestamp
    elsewhere at the same height would otherwise be mistaken for a
    countdown and block every click for the whole ad.

    Only the lower-right part of the screen is scanned (see
    SKIP_SCAN_LEFT / SKIP_SCAN_TOP) - much faster than OCR-ing the whole
    screen on every poll. Returns True if it clicked something.
    """
    full = pyautogui.screenshot()
    full_w, full_h = full.size
    off_x = int(full_w * config.SKIP_SCAN_LEFT)
    off_y = int(full_h * config.SKIP_SCAN_TOP)
    region = full.crop((off_x, off_y, full_w, full_h)).convert("L")

    t_scan = time.time()
    data = ocr_data(region)
    if data is None:
        return False

    if config.DEBUG_TIMING:
        seen = [w for w in data["text"] if "skip" in w.lower()]
        print(f"[skip scan {region.size[0]}x{region.size[1]} took {time.time() - t_scan:.1f}s"
              f" | words containing 'skip': {seen or 'none'}]")

    n = len(data["text"])

    for i, word in enumerate(data["text"]):
        if "skip" not in word.lower().strip():
            continue

        skip_left = data["left"][i]
        skip_width = data["width"][i]
        skip_height = data["height"][i]
        skip_right = skip_left + skip_width
        line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])

        # Only words physically near "skip" on the same line count as
        # part of its countdown - not anything else sharing that line.
        nearby_has_digit = False
        for j in range(n):
            if j == i:
                continue
            if (data["block_num"][j], data["par_num"][j], data["line_num"][j]) != line_key:
                continue
            if not data["text"][j].strip():
                continue
            distance = abs(data["left"][j] - skip_right)
            if distance > max(skip_width * 4, 150):
                continue  # too far away to be part of this button
            if re.search(r"\d", data["text"][j]):
                nearby_has_digit = True
                break

        if nearby_has_digit:
            if config.DEBUG_TIMING:
                print("[skip button found but a countdown number is next to it - waiting]")
            continue  # still counting down ("Skip Ad in 4") - not clickable yet

        # Convert screenshot pixels to mouse coordinates. On Windows with
        # display scaling (125%, 150%...) these differ.
        screen_w, screen_h = pyautogui.size()
        x = round((off_x + skip_left + skip_width // 2) * screen_w / full_w)
        y = round((off_y + data["top"][i] + skip_height // 2) * screen_h / full_h)
        if config.DEBUG_TIMING:
            print(f"[skip click at ({x}, {y}) | screenshot {full_w}x{full_h}, mouse space {screen_w}x{screen_h}]")
        pyautogui.click(x, y)
        return True

    return False
