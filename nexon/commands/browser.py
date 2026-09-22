"""
COMMANDS: web browser

  "search <query>"           -> opens Google AND reads the first result aloud
  "play <song> [on youtube]" -> opens the top YouTube result directly
  "open <site>"              -> SITE_SHORTCUTS (config.py) or a guessed URL
  "close all tabs"           -> Ctrl+Shift+W (checked BEFORE "close tab")
  "close tab"                -> Ctrl+W

This is the file the person adding nexon commands will edit most.
TO ADD A NEW BROWSER COMMAND: write the action function, then a
@command(...)-decorated handler below that calls it - nothing outside
this file needs to change, since nexon.commands/__init__.py already
imports this module once.

IMPORTANT ordering note: this module is imported (see commands/__init__)
AFTER nexon.commands.screen_reading (so "open/launch pdf ..." is claimed
there first) and BEFORE nexon.commands.media (so "play <song>" is
claimed here before media.py's generic "pause"/"play").
"""

import re
import threading
import webbrowser

import pywhatkit
import requests
from bs4 import BeautifulSoup

from ..config import SITE_SHORTCUTS
from ..helpers import speak_long_text
from ..registry import command
from ..tts import speak

import pyautogui  # noqa: F401  (kept available for future browser commands)


def _read_google_result(url):
    """Fetch the results page and read the top result aloud (runs on its own thread)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print(f"Search fetch error: {e}")
        speak("I opened the search, but couldn't fetch the results to read aloud.")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    result = next((b for b in soup.select("div.g") if b.find("h3")), None)
    if result is None:
        speak("I opened the search, but couldn't find a readable result.")
        return

    title = result.find("h3").get_text(strip=True)
    snippet_tag = result.find("span")
    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
    speak_long_text(f"{title}. {snippet}" if snippet else title, prefix="Top result:")


def google_search(query, read_result=True):
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
    webbrowser.open(url)
    if not read_result:
        return

    speak(f"Searching for {query}.", wait=False)
    # The network fetch happens in the background so nexon can take your
    # next command instead of freezing for up to 5 seconds.
    threading.Thread(target=_read_google_result, args=(url,), daemon=True).start()


def open_website(command_text):
    """Handle 'open <site>' by matching shortcuts or building a URL."""
    match = re.search(r"open (.+)", command_text)
    if not match:
        speak("Which website should I open?")
        return

    site = match.group(1).strip().rstrip(".")

    if site in SITE_SHORTCUTS:
        url = SITE_SHORTCUTS[site]
    elif site.startswith("http://") or site.startswith("https://"):
        url = site
    elif "." in site:
        url = f"https://{site}"
    else:
        url = f"https://{site}.com"

    webbrowser.open(url)
    speak(f"Opening {site}")


def close_tab():
    """
    Close the current tab (Ctrl+W). Just a keystroke sent to whatever
    window has focus - make sure a browser is focused.
    """
    pyautogui.hotkey("ctrl", "w")


def close_all_tabs():
    """
    Close all tabs in the current browser window (Ctrl+Shift+W). In most
    browsers this closes the entire window rather than closing tabs one
    at a time and leaving the window open.
    """
    pyautogui.hotkey("ctrl", "shift", "w")


def play_on_youtube(command_text):
    """Handle 'play <song/query> [on youtube]' by auto-playing the top result."""
    match = re.search(r"play (.+?)(?: on youtube)?$", command_text)
    query = match.group(1).strip() if match else command_text.replace("play", "", 1).strip()

    if not query:
        speak("What should I play?")
        return

    speak(f"Playing {query} on YouTube")
    try:
        pywhatkit.playonyt(query)
    except Exception as e:
        print(f"YouTube play error: {e}")
        speak("I couldn't play that on YouTube.")


# ---- registered commands, in original priority order ----

@command(lambda cmd: cmd.startswith("search "))
def handle_search(command_text):
    google_search(command_text[len("search "):].strip())


@command(lambda cmd: cmd.startswith("play "))
def handle_play_on_youtube(command_text):
    play_on_youtube(command_text)


@command(lambda cmd: cmd.startswith("open "))
def handle_open_website(command_text):
    open_website(command_text)


# Checked BEFORE the single-tab branch below, on purpose: "close all
# tabs" must never fall into "close tab" (or vice versa).
@command("close all tab")
def handle_close_all_tabs(command_text):
    close_all_tabs()
    speak("Closed all tabs", wait=False)


@command(["close tab", "close this tab", "close the tab", "close current tab"])
def handle_close_tab(command_text):
    close_tab()
    speak("Closed the tab", wait=False)
