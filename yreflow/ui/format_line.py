"""Standalone message line formatting — extracted from WolferyApp for testability."""

import re

from ..constants import NAMED_COLORS

_ELIDE_SPACE_CHARS = frozenset("',.!?:;-\u2019")


def _parse_css_color(color_str: str) -> tuple[int, int, int] | None:
    """Parse a CSS color string (hex, rgb(), named) into (r, g, b)."""
    s = color_str.strip().lower()
    m = re.match(r"^#([0-9a-f]{6})$", s)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.match(r"^#([0-9a-f]{3})$", s)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
    m = re.match(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    return None


def _luminance(r: int, g: int, b: int) -> float:
    """Relative luminance (0-1) per WCAG formula."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def format_timestamp(timestamp: str, focus_color: str | None) -> str:
    """Format the timestamp, applying focus background color if set."""
    if not timestamp:
        return ""
    if focus_color:
        rgb = _parse_css_color(focus_color)
        if rgb and _luminance(*rgb) > 0.3:
            fg = "#333333"
        else:
            fg = "#cccccc"
        return f"[{fg} on {focus_color}]{timestamp}[/] "
    return f"[dim]{timestamp}[/dim] "


def format_line(
    style: str,
    sender: str,
    msg: str,
    target_name: str,
    has_pose: bool,
    is_ooc: bool,
    timestamp: str,
    focus_color: str | None = None,
) -> str:
    """Format a single message line into Rich markup."""
    ts = format_timestamp(timestamp, focus_color)
    sep = "" if msg and msg[0] in _ELIDE_SPACE_CHARS else " "

    if is_ooc and style not in ("ooc",):
        msg = f"[dim]{msg}[/dim]"

    if style == "say":
        return f'{ts}[bold cyan]{sender}[/bold cyan] says, "{msg}"'

    if style == "pose":
        return f"{ts}[bold cyan]{sender}[/bold cyan]{sep}{msg}"

    if style == "ooc":
        if has_pose:
            return f"{ts}[dim]\\[OOC][/dim] [bold cyan]{sender}[/bold cyan]{sep}[dim]{msg}[/dim]"
        return f'{ts}[dim]\\[OOC][/dim] [bold cyan]{sender}[/bold cyan] [dim]says, "{msg}"[/dim]'

    if style == "whisper":
        label = f"[magenta]whisper {target_name}[/magenta]"
        if has_pose:
            return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}){sep}{msg}"
        return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) whispers, "{msg}"'

    if style == "message":
        label = f"[yellow]msg {target_name}[/yellow]"
        if has_pose:
            return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}){sep}{msg}"
        return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) messages, "{msg}"'

    if style == "address":
        label = f"[green]@{target_name}[/green]"
        if has_pose:
            return f"{ts}[bold cyan]{sender}[/bold cyan] ({label}){sep}{msg}"
        return f'{ts}[bold cyan]{sender}[/bold cyan] ({label}) says, "{msg}"'

    if style == "describe":
        return f"{ts}[italic]{msg}[/italic]{'[dim](' + sender + ')[/dim]' if sender != ' ' else ''}"

    if style in ("arrive", "leave", "travel", "sleep", "action", "wakeup"):
        return f"{ts}[dim][bold]{sender}[/bold] {msg}[/dim]"

    if style == "roll":
        return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"

    if style == "leadRequest":
        return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] wants to lead {target_name}.[/bold yellow]"

    if style == "followRequest":
        return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] wants to follow {target_name}.[/bold yellow]"

    if style == "controlRequest":
        return f"{ts}[bold yellow]>> [bold cyan]{sender}[/bold cyan] requests control of {target_name}.[/bold yellow]"

    # Fallback
    return f"{ts}[bold cyan]{sender}[/bold cyan] {msg}"
