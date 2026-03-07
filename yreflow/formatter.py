"""Convert Wolfery inline markup to Rich markup for terminal display.

Extracted and adapted from Samples/Gui.py:394-508.
HTML tags replaced with Rich console markup equivalents.
"""

import re
from collections.abc import Callable
from typing import Literal

from unicodeitplus import replace as upreplace
from lark.exceptions import UnexpectedCharacters, UnexpectedToken, UnexpectedEOF

# Placeholders for content extracted before character-level formatting
_LINK_PLACEHOLDER = "\x00LINK{}\x00"
_ESC_PLACEHOLDER = "\x00ESC{}\x00"
_CODE_PLACEHOLDER = "\x00CODE{}\x00"


def convert_string(
        text: str,
        converter: Literal['^','_']
) -> str:
    """
    Helper function converting latex using unicodeitplus
    """
    newstr = ""
    for char in text:
        try:
            unicode = upreplace(f"{converter}{char}")
        except (UnexpectedCharacters, UnexpectedEOF, UnexpectedToken):
            newstr += char
            continue
        if len(unicode) == 1:
            newstr += unicode
        else:
            newstr += char
    return newstr

def superscript_string(
        text: str
) -> str:
    """
    Convery a string to unicode superscript for available unicode characters
    """
    return convert_string(text, "^")

def subscript_string(
        text: str
) -> str:
    """
    Convery a string to unicode superscript for available unicode characters
    """
    return convert_string(text, "_")




def format_message(
    msg_text: str,
    on_url: Callable[[str, str], None] | None = None,
) -> str:
    """Convert Wolfery markup in a message to Rich markup.

    If *on_url* is provided it is called with ``(display_text, url)`` for every
    markdown-style link found in *msg_text*.
    """
    # Extract <esc>...</esc> blocks — content inside should not be formatted
    esc_blocks: list[str] = []

    def _replace_esc(m):
        idx = len(esc_blocks)
        esc_blocks.append(m.group(1))
        return _ESC_PLACEHOLDER.format(idx)

    msg_text = re.sub(r"<esc>(.*?)</esc>", _replace_esc, msg_text, flags=re.DOTALL)

    # Extract `code` spans — content inside should not be formatted, rendered in goldenrod
    code_blocks: list[str] = []

    def _replace_code(m):
        idx = len(code_blocks)
        code_blocks.append(m.group(1))
        return _CODE_PLACEHOLDER.format(idx)

    msg_text = re.sub(r"`(.*?)`", _replace_code, msg_text, flags=re.DOTALL)

    # First pass: extract markdown links before character-level processing
    # so they don't interfere with Rich markup brackets
    links: list[tuple[str, str]] = []
    url_find = r"\[([^\]]*?)\]\(([^)]*?)\)"

    def _replace_link(m):
        idx = len(links)
        links.append((m.group(1), m.group(2)))
        return _LINK_PLACEHOLDER.format(idx)

    msg_text = re.sub(url_find, _replace_link, msg_text)

    # Second pass: extract bare URLs not already wrapped in markdown link syntax
    def _replace_bare_url(m):
        idx = len(links)
        bare = m.group(0)
        links.append((bare, bare))
        return _LINK_PLACEHOLDER.format(idx)

    msg_text = re.sub(r"https?://[^\s<>\"'\])]*", _replace_bare_url, msg_text)

    # Notify caller about every URL we found
    if on_url and links:
        for text, url in links:
            on_url(text, url)

    # Strip <nobr> tags (Rich/Textual has no non-breaking span support)
    msg_text = re.sub(r"</?nobr>", "", msg_text)

    # Character-level formatting pass
    bold = False
    italic = False
    strike = False
    superscript = False
    subscript = False
    ooc = False

    out = ""
    skips: set[int] = set()

    for c in range(len(msg_text)):
        if c in skips:
            continue

        ch = msg_text[c]
        remaining = msg_text[c + 1 :] if c < len(msg_text) - 1 else ""
        next_ch = msg_text[c + 1] if c < len(msg_text) - 1 else ""
        prev_ch = msg_text[c - 1] if c > 0 else ""

        # Italic: _text_
        if ch == "_" and not italic and "_" in remaining:
            if c == 0 or not prev_ch.isalnum():
                italic = True
                out += "[italic]"
                continue
        if ch == "_" and italic:
            if c == len(msg_text) - 1 or not next_ch.isalnum():
                italic = False
                out += "[/italic]"
                continue

        # Bold: **text**
        if ch == "*" and next_ch == "*" and not bold:
            bold = True
            out += "[bold]"
            skips.add(c + 1)
            continue
        if ch == "*" and next_ch == "*" and bold:
            bold = False
            out += "[/bold]"
            skips.add(c + 1)
            continue

        # Strikethrough: ~~text~~
        if ch == "~" and next_ch == "~" and not strike:
            strike = True
            out += "[strike]"
            skips.add(c + 1)
            continue
        if ch == "~" and next_ch == "~" and strike:
            strike = False
            out += "[/strike]"
            skips.add(c + 1)
            continue

        # Superscript: ++text++ (Approximated with unicode)
        if ch == "+" and next_ch == "+" and not superscript:
            superscript = True
            out += ""
            skips.add(c + 1)
            continue
        if ch == "+" and next_ch == "+" and superscript:
            superscript = False
            out += ""
            skips.add(c + 1)
            continue

        # Subscript: --text-- (approximated with unicode)
        if ch == "-" and next_ch == "-" and not subscript:
            subscript = True
            out += ""
            skips.add(c + 1)
            continue
        if ch == "-" and next_ch == "-" and subscript:
            subscript = False
            out += ""
            skips.add(c + 1)
            continue

        # OOC inline: ((text))
        if ch == "(" and next_ch == "(" and not ooc:
            ooc = True
            out += "[dim]("
            skips.add(c + 1)
            continue
        if ch == ")" and next_ch == ")" and ooc:
            ooc = False
            out += ")[/dim]"
            skips.add(c + 1)
            continue

        # Escape Rich markup characters
        if ch == "[":
            out += "\\["
            continue
        
        if superscript:
            ch = superscript_string(ch)

        if subscript:
            ch = subscript_string(ch)

        out += ch

    # Restore link placeholders – render as underlined cyan text.
    # Rich's [link=URL] syntax chokes on special chars in URLs (://, etc.),
    # so we avoid it and just style the visible text.
    for i, (text, url) in enumerate(links):
        placeholder = _LINK_PLACEHOLDER.format(i)
        safe_text = text.replace("[", "\\[")
        out = out.replace(placeholder, f"[underline cyan]{safe_text}[/underline cyan]")

    # Restore `code` spans as goldenrod escaped text (no formatting applied)
    for i, raw in enumerate(code_blocks):
        placeholder = _CODE_PLACEHOLDER.format(i)
        safe = raw.replace("[", "\\[")
        out = out.replace(placeholder, f"[dark_goldenrod]{safe}[/dark_goldenrod]")

    # Restore <esc> blocks as plain escaped text (no formatting applied)
    for i, raw in enumerate(esc_blocks):
        placeholder = _ESC_PLACEHOLDER.format(i)
        safe = raw.replace("[", "\\[")
        out = out.replace(placeholder, safe)

    return out
