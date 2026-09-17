# Nexon — Command Reference

Say **"nexon"** first, then the command below (e.g. "nexon volume up").
Say **"nexon stay awake"** to skip saying "nexon" every time; say **"sleep"**
(or "nexon sleep") to go back to normal.

## Mode
| Say | Effect |
|---|---|
| stay awake | Stops requiring "nexon" before each command |
| sleep / go to sleep / stop listening | Goes back to requiring "nexon" first |
| shutdown assistant / exit / quit / goodbye | Closes nexon |

## Timers & Stopwatch
| Say | Effect |
|---|---|
| set a timer for \<duration\> / timer for \<duration\> | Starts a countdown timer (rings when done) |
| cancel timer(s) / stop the timer | Cancels all running countdown timers |
| start timer / start stopwatch | Starts the stopwatch |
| stop timer / stop stopwatch | Stops the stopwatch and reports elapsed time |

## Volume & Brightness
| Say | Effect |
|---|---|
| volume up / increase volume | Raises volume one step |
| volume down / decrease volume | Lowers volume one step |
| set volume to \<number\> / volume to \<number\> | Sets volume to an exact level |
| mute | Mutes audio |
| brightness up / increase brightness | Raises screen brightness one step |
| brightness down / decrease brightness | Lowers screen brightness one step |
| set brightness to \<number\> / brightness to \<number\> | Sets brightness to an exact level |

## Screen, WhatsApp & PDFs
| Say | Effect |
|---|---|
| read screen / what's on my screen | OCRs and reads the screen aloud (auto-detects an open PDF and reads real text instead) |
| read whatsapp / whatsapp messages / new messages | Reads new text visible in the WhatsApp Desktop window |
| read pdf \<filename\> | Finds and opens a PDF by name, loads it into nexon, reads page 1 |
| read page \<number\> | Reads a specific page of the loaded PDF |
| next page | Reads the next page of the loaded PDF |
| previous page / last page / go back a page | Reads the previous page of the loaded PDF |
| launch pdf \<filename\> / open pdf \<filename\> | Opens a PDF in your default PDF viewer (not read aloud) |
| screenshot / take a screenshot | Takes and saves a screenshot |

## Clicking, Scrolling & Typing
| Say | Effect |
|---|---|
| click \<text on screen\> | Clicks the on-screen text that best matches |
| double click \<text on screen\> | Double-clicks the on-screen text that best matches |
| scroll up [number] | Scrolls up (default step, or a specific amount) |
| scroll down [number] | Scrolls down (default step, or a specific amount) |
| type \<text\> | Types the text into whatever field has focus |
| type \<text\> and enter / type \<text\> and search | Types the text and submits it |
| dictate / type a message | Listens for spoken text, then types it |
| send message \<text\> | Types and sends a chat message (presses Enter) |

## Files
| Say | Effect |
|---|---|
| delete file / delete this file / delete | Deletes the currently selected file (to Recycle Bin) |
| delete file permanently / delete this file forever | Permanently deletes the selected file (skips Recycle Bin) |
| clear recycle bin / empty recycle bin | Empties the Recycle Bin |

## Web Browser
| Say | Effect |
|---|---|
| open \<site\> | Opens a website (shortcuts: youtube, google, gmail, whatsapp, github, facebook, twitter/x, reddit, netflix, amazon, ao3) |
| search \<query\> | Opens a Google search and reads the top result aloud |
| play \<song/query\> [on youtube] | Plays the top YouTube result for the query |
| close tab / close this tab | Closes the current browser tab (Ctrl+W) |
| close all tabs | Closes the whole browser window (Ctrl+Shift+W) |

## Media Playback
| Say | Effect |
|---|---|
| pause / play | Toggles play/pause on the active media |
| next video / next | Skips to the next video |
| previous video / last video | Goes back to the previous video |
| skip ad / skip the ad | Skips a playing ad |

## Notes
- **click / double click** only work on visible, readable text (a button label, a title) — not bare icons.
- **close tab / close all tabs** and **delete file** send raw keystrokes to whichever window is focused, so make sure the right window (browser / File Explorer) is active first.
- **read pdf / launch pdf** use fuzzy filename matching, so an approximate name usually works.
- Kill switch (not spoken): press **Ctrl+Alt+J** to force-quit nexon immediately.
