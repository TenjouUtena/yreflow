"""Convert Wolfery inline markup to Rich markup for terminal display.

Extracted and adapted from Samples/Gui.py:394-508.
HTML tags replaced with Rich console markup equivalents.
"""

import re

# Placeholder for links extracted before character-level formatting
_LINK_PLACEHOLDER = "\x00LINK{}\x00"


def format_message(msg_text: str) -> str:
    """Convert Wolfery markup in a message to Rich markup."""
    # First pass: extract markdown links before character-level processing
    # so they don't interfere with Rich markup brackets
    links: list[tuple[str, str]] = []
    url_find = r"\[([^\]]*?)\]\(([^)]*?)\)"

    def _replace_link(m):
        idx = len(links)
        links.append((m.group(1), m.group(2)))
        return _LINK_PLACEHOLDER.format(idx)

    msg_text = re.sub(url_find, _replace_link, msg_text)

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

        # Superscript: ++text++ (approximated as dim in terminal)
        if ch == "+" and next_ch == "+" and not superscript:
            superscript = True
            out += "[dim]^"
            skips.add(c + 1)
            continue
        if ch == "+" and next_ch == "+" and superscript:
            superscript = False
            out += "[/dim]"
            skips.add(c + 1)
            continue

        # Subscript: --text-- (approximated as dim in terminal)
        if ch == "-" and next_ch == "-" and not subscript:
            subscript = True
            out += "[dim]_"
            skips.add(c + 1)
            continue
        if ch == "-" and next_ch == "-" and subscript:
            subscript = False
            out += "[/dim]"
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

        out += ch

    # Restore link placeholders – render as underlined cyan text.
    # Rich's [link=URL] syntax chokes on special chars in URLs (://, etc.),
    # so we avoid it and just style the visible text.
    for i, (text, url) in enumerate(links):
        placeholder = _LINK_PLACEHOLDER.format(i)
        safe_text = text.replace("[", "\\[")
        out = out.replace(placeholder, f"[underline cyan]{safe_text}[/underline cyan]")

    return out
