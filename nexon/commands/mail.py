"""
COMMANDS: email

  "check email" / "check my mail" / "any new emails"   -> unread count +
                                                            sender/subject,
                                                            across EMAIL_FOLDERS
  "check email in <folder>"                             -> just that folder
  "read email" / "read latest email"                    -> speaks the newest
                                                            unread email's body

Uses only imaplib + email from the standard library - no paid API, no
extra pip install, works with any IMAP provider. Set IMAP_HOST,
IMAP_USER, IMAP_PASSWORD, and EMAIL_FOLDERS in nexon/config.py (see
README.md for the Gmail app-password steps).
"""

import email
import imaplib
import re
from email.header import decode_header

from ..config import EMAIL_FOLDERS, IMAP_HOST, IMAP_PASSWORD, IMAP_USER, MAX_EMAILS_SPOKEN
from ..helpers import speak_long_text
from ..registry import command
from ..tts import speak


def _decode(value):
    """Decode a MIME-encoded header ('=?UTF-8?B?...?=') into plain text."""
    if not value:
        return ""
    decoded = ""
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            decoded += text.decode(charset or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


def _sender_name(from_header):
    """'"Jane Doe" <jane@x.com>' -> 'Jane Doe' (falls back to the raw header if there's no display name)."""
    text = _decode(from_header)
    match = re.match(r'^"?([^"<]*)"?\s*<', text)
    name = match.group(1).strip() if match else text
    return name or text


def _connect():
    if not IMAP_USER or not IMAP_PASSWORD:
        speak("Email isn't set up yet. Add your email address and app password as environment variables.")
        return None
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST)
        conn.login(IMAP_USER, IMAP_PASSWORD)
        return conn
    except imaplib.IMAP4.error as e:
        print(f"IMAP login error: {e}")
        speak("I couldn't log into your email. Check your username and app password.")
        return None
    except OSError as e:
        print(f"IMAP connection error: {e}")
        speak("I couldn't reach the mail server. Check your internet connection.")
        return None


def _unread_in_folder(conn, folder):
    """Returns (list of (sender, subject) - newest first, capped at MAX_EMAILS_SPOKEN; total unread count)."""
    status, _ = conn.select(f'"{folder}"', readonly=True)
    if status != "OK":
        return None

    status, data = conn.search(None, "UNSEEN")
    if status != "OK" or not data[0]:
        return [], 0

    ids = data[0].split()
    preview = []
    for msg_id in reversed(ids):
        if len(preview) >= MAX_EMAILS_SPOKEN:
            break
        status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        if status != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        preview.append((_sender_name(msg.get("From")), _decode(msg.get("Subject")) or "(no subject)"))

    return preview, len(ids)


def check_email(folders=None):
    """Speak the unread count (and sender/subject) across `folders` (defaults to EMAIL_FOLDERS)."""
    folders = folders or EMAIL_FOLDERS
    conn = _connect()
    if conn is None:
        return

    try:
        found_any = False
        for folder in folders:
            outcome = _unread_in_folder(conn, folder)
            if outcome is None:
                speak(f"I couldn't find a folder called {folder}.")
                continue

            preview, count = outcome
            if count == 0:
                continue

            found_any = True
            label = f" in {folder}" if len(folders) > 1 else ""
            speak(f"{count} unread email{'s' if count != 1 else ''}{label}.")
            for sender, subject in preview:
                speak(f"From {sender}: {subject}")

        if not found_any:
            speak("No unread email.")
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def read_latest_email():
    """Read the newest unread email's body aloud, from the first folder in EMAIL_FOLDERS."""
    conn = _connect()
    if conn is None:
        return

    try:
        folder = EMAIL_FOLDERS[0]
        status, _ = conn.select(f'"{folder}"', readonly=True)
        if status != "OK":
            speak(f"I couldn't find a folder called {folder}.")
            return

        status, data = conn.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            speak("No unread email.")
            return

        latest_id = data[0].split()[-1]
        status, msg_data = conn.fetch(latest_id, "(RFC822)")
        if status != "OK":
            speak("I couldn't fetch that email.")
            return

        msg = email.message_from_bytes(msg_data[0][1])
        sender = _sender_name(msg.get("From"))
        subject = _decode(msg.get("Subject")) or "(no subject)"

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
        else:
            charset = msg.get_content_charset() or "utf-8"
            body = msg.get_payload(decode=True).decode(charset, errors="replace")

        speak_long_text(body or "This email doesn't have a readable text version.",
                         prefix=f"From {sender}, subject: {subject}.")
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ---- registered commands ----
# ("check email in <folder>" is checked BEFORE the plain "check email"
# below, so a folder name is never swallowed by the all-folders version.)

@command(lambda cmd: cmd.startswith("check email in ") or cmd.startswith("check mail in "))
def handle_check_email_in_folder(command_text):
    folder = re.sub(r"^check (email|mail) in ", "", command_text).strip()
    check_email(folders=[folder] if folder else None)


@command(["check email", "check my email", "check mail", "check my mail", "any new emails", "any new email"])
def handle_check_email(command_text):
    check_email()


@command(["read email", "read my email", "read latest email", "read my latest email"])
def handle_read_email(command_text):
    read_latest_email()
