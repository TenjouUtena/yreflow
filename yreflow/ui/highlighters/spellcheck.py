"""Inline spellcheck highlighter for the input bar.

Uses pyspellchecker to identify misspelled words and underlines them
in red.  Lazy-loads the checker on first use to avoid startup cost.
"""

import re

from rich.highlighter import Highlighter
from rich.text import Text

# Words consisting of letters and apostrophes (contractions like "don't")
_WORD_RE = re.compile(r"[a-zA-Z'\u2019]+")

# Command prefixes to skip past before spellchecking.
# Matches: say, ooc, pose, go, teleport, home, sweep, status, release,
# focus, unfocus, summon, join, lead, follow, profile, morph, look, laston,
# wa, wh, w, p, m, l, t  plus single-char prefixes : " > @
_CMD_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:say|ooc|pose|go|teleport|home|sweep|status|release|"
    r"focus|unfocus|summon|join|lead|follow|profile|morph|look|laston|wa|wh?|[pmlt])\s"
    r"|[:\"\u201c\u201d>@]"
    r")"
)

_MISSPELLED_STYLE = "underline red"


class SpellCheckHighlighter(Highlighter):
    """Highlights misspelled words with an underline.

    Caches results per input string so repeated renders (cursor blink,
    etc.) don't re-run the checker.
    """

    def __init__(self) -> None:
        self._checker = None  # lazy-loaded SpellChecker
        self._custom_words: set[str] = set()
        # Cache: plain text -> list of (start, end) spans
        self._cache_key: str = ""
        self._cache_spans: list[tuple[int, int]] = []

    def _ensure_checker(self):
        """Lazy-load spellchecker on first use."""
        if self._checker is None:
            from spellchecker import SpellChecker

            self._checker = SpellChecker()
            if self._custom_words:
                self._checker.word_frequency.load_words(self._custom_words)

    def update_custom_words(self, words: set[str]) -> None:
        """Replace the custom dictionary (character names, game terms, etc.)."""
        self._custom_words = {w.lower() for w in words if w}
        if self._checker is not None:
            self._checker.word_frequency.load_words(self._custom_words)
        # Invalidate cache since known-words changed
        self._cache_key = ""

    def _content_offset(self, plain: str) -> int:
        """Return char offset where prose begins, past any command prefix."""
        m = _CMD_PREFIX_RE.match(plain)
        if not m:
            return 0

        offset = m.end()

        # For whisper/page/message commands (w, wh, p, m): skip past 'Name='
        prefix = m.group()
        if re.match(r"^(?:wh?|[pm])\s", prefix):
            eq_pos = plain.find("=", offset)
            if eq_pos != -1:
                offset = eq_pos + 1

        return offset

    def _find_misspelled_spans(self, plain: str) -> list[tuple[int, int]]:
        """Find (start, end) spans of misspelled words."""
        self._ensure_checker()

        offset = self._content_offset(plain)
        prose = plain[offset:]

        word_spans = []
        for match in _WORD_RE.finditer(prose):
            word = match.group()
            if len(word) <= 1:
                continue
            start = match.start() + offset
            end = match.end() + offset
            if end != len(plain):
                word_spans.append((word.lower(), start, end))

        if not word_spans:
            return []

        # Batch check all words at once
        words_to_check = [w for w, _, _ in word_spans]
        misspelled = self._checker.unknown(words_to_check)

        return [(s, e) for w, s, e in word_spans if w in misspelled]

    def highlight(self, text: Text) -> None:
        plain = text.plain
        if not plain.strip():
            return

        # Reuse cache if text hasn't changed
        if plain != self._cache_key:
            self._cache_key = plain
            self._cache_spans = self._find_misspelled_spans(plain)

        for start, end in self._cache_spans:
            text.stylize(_MISSPELLED_STYLE, start, end)
