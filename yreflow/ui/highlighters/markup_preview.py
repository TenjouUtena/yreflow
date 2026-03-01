"""Live preview of Wolfery inline markup in the input bar.

Mirrors the markup patterns in formatter.py but applies Rich styles
in-place via Text.stylize() rather than converting to markup strings.
"""

import re

from rich.highlighter import Highlighter
from rich.text import Text

# Each entry: (compiled regex, content_style, delimiter_style)
# Named groups: 'open' = opening delimiter, 'content' = inner text, 'close' = closing delimiter
_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Bold: **text**
    (re.compile(r"(?P<open>\*\*)(?P<content>.+?)(?P<close>\*\*)"), "bold", "dim"),
    # Italic: _text_ (not surrounded by alphanumerics)
    (
        re.compile(r"(?<![a-zA-Z0-9])(?P<open>_)(?P<content>.+?)(?P<close>_)(?![a-zA-Z0-9])"),
        "italic",
        "dim",
    ),
    # Strikethrough: ~~text~~
    (re.compile(r"(?P<open>~~)(?P<content>.+?)(?P<close>~~)"), "strike", "dim"),
    # OOC inline: ((text))
    (re.compile(r"(?P<open>\(\()(?P<content>.+?)(?P<close>\)\))"), "dim", "dim yellow"),
    # Superscript: ++text++
    (re.compile(r"(?P<open>\+\+)(?P<content>.+?)(?P<close>\+\+)"), "dim", "dim"),
    # Subscript: --text--
    (re.compile(r"(?P<open>--)(?P<content>.+?)(?P<close>--)"), "dim", "dim"),
    # Links: [text](url)
    (re.compile(r"(?P<open>\[)(?P<content>[^\]]+?)(?P<close>\]\([^)]*\))"), "underline cyan", "dim"),
]


class MarkupPreviewHighlighter(Highlighter):
    """Highlights Wolfery markup delimiters and previews their formatting.

    Delimiters are dimmed; content between them gets the actual style applied,
    giving a live WYSIWYG-like preview as the user types.
    """

    def highlight(self, text: Text) -> None:
        plain = text.plain
        if not plain:
            return

        for pattern, content_style, delim_style in _PATTERNS:
            for match in pattern.finditer(plain):
                # Dim the delimiters
                open_start, open_end = match.span("open")
                close_start, close_end = match.span("close")
                text.stylize(delim_style, open_start, open_end)
                text.stylize(delim_style, close_start, close_end)

                # Style the content
                content_start, content_end = match.span("content")
                text.stylize(content_style, content_start, content_end)
