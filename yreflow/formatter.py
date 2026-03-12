"""Convert Wolfery inline markup to Rich markup for terminal display.

Extracted and adapted from Samples/Gui.py:394-508.
HTML tags replaced with Rich console markup equivalents.
"""

import re
from collections.abc import Callable
from typing import Literal

from unicodeitplus import replace as upreplace
from lark.exceptions import UnexpectedCharacters, UnexpectedToken, UnexpectedEOF

from yreflow.constants import NAMED_COLORS

# Placeholders for content extracted before character-level formatting
_LINK_PLACEHOLDER = "\x00LINK{}\x00"
_ESC_PLACEHOLDER = "\x00ESC{}\x00"
_CODE_PLACEHOLDER = "\x00CODE{}\x00"
_FENCED_PLACEHOLDER = "\x00FENCED{}\x00"
_BLOCK_PLACEHOLDER = "\x00BLOCK{}\x00"


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




def _is_table_row(stripped: str) -> bool:
    """Check if a line looks like a table row (contains | as column delimiter)."""
    if "|" not in stripped:
        return False
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    return len(cells) >= 2


def _format_table(lines: list[str]) -> str:
    """Convert markdown-style table lines into aligned Rich markup."""
    rows: list[list[str]] = []
    separator_idx: int | None = None
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^-{3,}$", c) for c in cells):
            separator_idx = i
            continue
        rows.append(cells)

    if not rows:
        return "\n".join(lines)

    # Calculate column widths
    num_cols = max(len(r) for r in rows)
    widths = [0] * num_cols
    for row in rows:
        for j, cell in enumerate(row):
            if j < num_cols:
                widths[j] = max(widths[j], len(cell))

    # If separator is the first line, there is no header row —
    # bold the first column of each data row instead.
    first_col_header = separator_idx == 0

    result_lines = []
    for i, row in enumerate(rows):
        parts = []
        for j in range(num_cols):
            cell = row[j] if j < len(row) else ""
            parts.append(cell.ljust(widths[j]))
        if first_col_header:
            line_text = " │ ".join([f"[bold]{parts[0]}[/bold]"] + parts[1:])
            result_lines.append(line_text)
        elif i == 0 and separator_idx is not None:
            # Header row
            line_text = " │ ".join(parts)
            result_lines.append(f"[bold]{line_text}[/bold]")
            result_lines.append("─┼─".join("─" * w for w in widths))
        else:
            line_text = " │ ".join(parts)
            result_lines.append(line_text)

    return "\n".join(result_lines)


def format_message(
    msg_text: str,
    on_url: Callable[[str, str], None] | None = None,
    superscript_style: str = "unicode",
    superscript_color: str = "gold",
    subscript_style: str = "unicode",
    subscript_color: str = "skyblue",
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

    # Extract fenced code blocks (``` ... ```) — no formatting, dark background
    fenced_blocks: list[str] = []

    def _replace_fenced(m):
        idx = len(fenced_blocks)
        fenced_blocks.append(m.group(1))
        return _FENCED_PLACEHOLDER.format(idx)

    msg_text = re.sub(
        r"^```[^\n]*\n(.*?)^```",
        _replace_fenced,
        msg_text,
        flags=re.DOTALL | re.MULTILINE,
    )

    # Extract `code` spans — content inside should not be formatted, rendered in goldenrod
    code_blocks: list[str] = []

    def _replace_code(m):
        idx = len(code_blocks)
        code_blocks.append((m.group(1),m.group(2)))
        return _CODE_PLACEHOLDER.format(idx)

    msg_text = re.sub(r"`(.*?)`(\W)", _replace_code, msg_text, flags=re.DOTALL)
    msg_text = re.sub(r"`(.*?)`()$", _replace_code, msg_text, flags=re.DOTALL)

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

    # Block-level formatting: headers, sections, tables
    # Pre-formatted blocks are stored as placeholders to survive char-level escaping
    block_results: list[str] = []

    def _store_block(rich_text: str) -> str:
        idx = len(block_results)
        block_results.append(rich_text)
        return _BLOCK_PLACEHOLDER.format(idx)

    processed_lines: list[str] = []
    raw_lines = msg_text.split("\n")
    table_buffer: list[str] = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        stripped = line.strip()

        # Flush table buffer if current line is not a table row
        if table_buffer and not _is_table_row(stripped):
            processed_lines.append(_store_block(_format_table(table_buffer)))
            table_buffer = []

        # Table row: contains | as column delimiter
        if _is_table_row(stripped):
            table_buffer.append(stripped)
            i += 1
            continue

        # Headers: # at start of line
        header_m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if header_m:
            level = len(header_m.group(1))
            header_text = header_m.group(2)
            if level == 1:
                processed_lines.append(_store_block(f"[bold underline]{header_text}[/bold underline]"))
            elif level == 2:
                processed_lines.append(_store_block(f"[bold]{header_text}[/bold]"))
            else:
                processed_lines.append(_store_block(f"[bold dim]{header_text}[/bold dim]"))
            i += 1
            continue

        # Section: [[title]] — limited (with { ... }) or open
        section_m = re.match(r"^\[\[(.*?)\]\](.*)$", stripped)
        if section_m:
            title = section_m.group(1)
            remainder = section_m.group(2).strip()

            # Determine if this is a limited section (has { ... } body)
            has_brace = False
            after_brace = ""

            if remainder.startswith("{"):
                has_brace = True
                after_brace = remainder[1:]
            elif not remainder and i + 1 < len(raw_lines) and raw_lines[i + 1].strip().startswith("{"):
                has_brace = True
                i += 1
                after_brace = raw_lines[i].strip()[1:]

            if has_brace:
                # Limited section
                processed_lines.append(_store_block(f"[bold cyan]▸ {title}[/bold cyan]"))

                # Handle content after { (possibly closing } on same line)
                if "}" in after_brace:
                    content = after_brace[:after_brace.index("}")]
                    if content.strip():
                        processed_lines.append(f"  {content.strip()}")
                    i += 1
                    continue

                if after_brace.strip():
                    processed_lines.append(f"  {after_brace.strip()}")

                # Collect content until closing }
                i += 1
                while i < len(raw_lines):
                    line_content = raw_lines[i]
                    if "}" in line_content:
                        before_brace = line_content[:line_content.index("}")]
                        if before_brace.strip():
                            processed_lines.append(f"  {before_brace.strip()}")
                        i += 1
                        break
                    processed_lines.append(f"  {line_content}")
                    i += 1
                continue
            else:
                # Open section
                processed_lines.append(_store_block(f"[bold cyan]▸ {title}[/bold cyan]"))
                i += 1
                continue

        processed_lines.append(line)
        i += 1

    # Flush any remaining table buffer
    if table_buffer:
        processed_lines.append(_store_block(_format_table(table_buffer)))

    msg_text = "\n".join(processed_lines)

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

        # Superscript: ++text++ (Unicode or highlight)
        if ch == "+" and next_ch == "+" and not superscript and "++" in msg_text[c + 2 :]:
            superscript = True
            if superscript_style == "highlight":
                out += f"[rgb({NAMED_COLORS[superscript_color][0]},{NAMED_COLORS[superscript_color][1]},{NAMED_COLORS[superscript_color][2]})]"
            skips.add(c + 1)
            continue
        if ch == "+" and next_ch == "+" and superscript:
            superscript = False
            if superscript_style == "highlight":
                out += f"[/rgb({NAMED_COLORS[superscript_color][0]},{NAMED_COLORS[superscript_color][1]},{NAMED_COLORS[superscript_color][2]})]"
            skips.add(c + 1)
            continue

        # Subscript: --text-- (Unicode or highlight)
        if ch == "-" and next_ch == "-" and not subscript and "--" in msg_text[c + 2 :]:
            subscript = True
            if subscript_style == "highlight":
                out += f"[rgb({NAMED_COLORS[subscript_color][0]},{NAMED_COLORS[subscript_color][1]},{NAMED_COLORS[subscript_color][2]})]"
            skips.add(c + 1)

            continue

        if ch == "-" and next_ch == "-" and subscript:
            subscript = False
            if subscript_style == "highlight":
                out += f"[/rgb({NAMED_COLORS[subscript_color][0]},{NAMED_COLORS[subscript_color][1]},{NAMED_COLORS[subscript_color][2]})]"
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
        
        if superscript and superscript_style == "unicode":
            ch = superscript_string(ch)

        if subscript and subscript_style == "unicode":
            ch = subscript_string(ch)

        out += ch

    # Restore block-level formatted content (headers, sections, tables)
    for i, rich_text in enumerate(block_results):
        placeholder = _BLOCK_PLACEHOLDER.format(i)
        out = out.replace(placeholder, rich_text)

    # Restore link placeholders – render as underlined cyan text.
    # Rich's [link=URL] syntax chokes on special chars in URLs (://, etc.),
    # so we avoid it and just style the visible text.
    for i, (text, url) in enumerate(links):
        placeholder = _LINK_PLACEHOLDER.format(i)
        safe_text = text.replace("[", "\\[")
        out = out.replace(placeholder, f"[underline cyan]{safe_text}[/underline cyan]")

    # Restore fenced code blocks with dark background
    for i, raw in enumerate(fenced_blocks):
        placeholder = _FENCED_PLACEHOLDER.format(i)
        safe = raw.replace("[", "\\[")
        out = out.replace(
            placeholder,
            f"[on grey15 dark_goldenrod]{safe}[/on grey15 dark_goldenrod]",
        )

    # Restore `code` spans as goldenrod escaped text (no formatting applied)
    for i, (raw, spc) in enumerate(code_blocks):
        placeholder = _CODE_PLACEHOLDER.format(i)
        safe = raw.replace("[", "\\[")
        out = out.replace(placeholder, f"[dark_goldenrod]{safe}[/dark_goldenrod]{spc}")

    # Restore <esc> blocks as plain escaped text (no formatting applied)
    for i, raw in enumerate(esc_blocks):
        placeholder = _ESC_PLACEHOLDER.format(i)
        safe = raw.replace("[", "\\[")
        out = out.replace(placeholder, safe)

    return out
