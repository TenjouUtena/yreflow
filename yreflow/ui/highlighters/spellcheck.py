"""Inline spellcheck highlighter for the input bar.

Uses a tiered backend system for spell checking:
1. macOS NSSpellChecker (via PyObjC) — respects system locale
2. pyenchant (cross-platform) — supports locale-specific dictionaries
3. pyspellchecker (fallback) — American English only

Eagerly loads the checker at construction time so the import cost
is paid at startup rather than blocking the UI thread mid-keystroke.
"""

import locale
import os
import re
import sys

from rich.highlighter import Highlighter
from rich.text import Text

# Words consisting of letters and apostrophes (contractions like "don't")
_WORD_RE = re.compile(r"[a-zA-Z'\u2019]+")

# Command prefixes to skip past before spellchecking.
# Matches all character and console commands that take arguments,
# plus single-char prefixes : " > @
_CMD_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:say|ooc|pose|go|teleport|tport|home|sweep|status|release|"
    r"focus|unfocus|summon|join|lead|follow|profile|morph|look|lookup|laston|"
    r"address|to|describe|desc|spoof|whois|wi|watch|unwatch|mail|roll|lfrp|"
    r"lookupname|create|realm|"
    r"(?:un)?mute\s(?:travel|ooc)|stop\s(?:follow|lead|lfrp)|area\srules|"
    r"wa|wh?|[pmlt])\s"
    r"|[:\"\u201c\u201d>@]"
    r")"
)

# Standalone command words that should never be flagged as misspelled.
# These are commands typed without arguments (e.g. "nav", "lfrp", "quit").
_COMMAND_WORDS = frozenset({
    "say", "ooc", "pose", "go", "teleport", "tport", "home", "sweep",
    "status", "release", "quit", "sleep", "focus", "unfocus", "summon",
    "join", "lead", "follow", "profile", "morph", "look", "lookup",
    "laston", "wa", "whereat", "whois", "wi", "address", "describe",
    "desc", "spoof", "watch", "unwatch", "mail", "roll", "lfrp",
    "nav", "settings", "lookupname", "create", "realm", "help",
    "mute", "unmute",
})

_MISSPELLED_STYLE = "underline red"


# ---------------------------------------------------------------------------
# Spell-check backends
# ---------------------------------------------------------------------------

class _NSSpellBackend:
    """macOS native spellchecker via PyObjC. Respects system locale."""

    def __init__(self):
        from AppKit import NSSpellChecker  # noqa: F401

        self._checker = NSSpellChecker.sharedSpellChecker()

    def unknown(self, words: list[str]) -> set[str]:
        checker = self._checker
        result = set()
        for word in words:
            rng = checker.checkSpellingOfString_startingAt_(word, 0)
            if rng.length > 0:
                result.add(word)
        return result

    def add_words(self, words: set[str]) -> None:
        for word in words:
            self._checker.learnWord_(word)


class _EnchantBackend:
    """Cross-platform spellchecker via pyenchant. Supports locale dictionaries."""

    def __init__(self):
        import enchant  # noqa: F401

        lang = self._detect_locale()
        try:
            self._dict = enchant.Dict(lang)
        except enchant.errors.DictNotFoundError:
            # Fall back to plain "en" or whatever is available
            self._dict = enchant.Dict("en")

    @staticmethod
    def _detect_locale() -> str:
        """Determine the best locale tag for enchant (e.g. 'en_GB')."""
        # Explicit env override
        lang = os.environ.get("LANG", "")
        if lang:
            tag = lang.split(".")[0]  # strip encoding e.g. en_GB.UTF-8 -> en_GB
            if tag:
                return tag
        # System locale
        loc = locale.getlocale()[0]
        if loc:
            return loc
        return "en_US"

    def unknown(self, words: list[str]) -> set[str]:
        check = self._dict.check
        return {w for w in words if not check(w)}

    def add_words(self, words: set[str]) -> None:
        add = self._dict.add
        for word in words:
            add(word)


class _PySpellBackend:
    """Fallback using pyspellchecker (American English only)."""

    def __init__(self):
        from spellchecker import SpellChecker

        self._checker = SpellChecker()

    def unknown(self, words: list[str]) -> set[str]:
        return self._checker.unknown(words)

    def add_words(self, words: set[str]) -> None:
        self._checker.word_frequency.load_words(words)


def _create_backend():
    """Try backends in priority order and return the first that works."""
    if sys.platform == "darwin":
        try:
            return _NSSpellBackend()
        except ImportError:
            pass
    if sys.platform != "win32":
        try:
            return _EnchantBackend()
        except ImportError:
            pass
    return _PySpellBackend()


# ---------------------------------------------------------------------------
# Highlighter
# ---------------------------------------------------------------------------

class SpellCheckHighlighter(Highlighter):
    """Highlights misspelled words with an underline.

    Caches results per input string so repeated renders (cursor blink,
    etc.) don't re-run the checker.
    """

    def __init__(self) -> None:
        self._checker = _create_backend()
        self._custom_words: set[str] = set()
        # Cache: plain text -> list of (start, end) spans
        self._cache_key: str = ""
        self._cache_spans: list[tuple[int, int]] = []

    def update_custom_words(self, words: set[str]) -> None:
        """Replace the custom dictionary (character names, game terms, etc.)."""
        self._custom_words = {w.lower() for w in words if w}
        self._checker.add_words(self._custom_words)
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

        # Batch check all words at once, excluding known command words
        words_to_check = [w for w, _, _ in word_spans if w not in _COMMAND_WORDS]
        misspelled = self._checker.unknown(words_to_check) if words_to_check else set()

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
