"""Input bar highlighters for spellcheck and markup preview."""

from .composite import CompositeHighlighter
from .markup_preview import MarkupPreviewHighlighter
from .spellcheck import SpellCheckHighlighter

__all__ = ["CompositeHighlighter", "MarkupPreviewHighlighter", "SpellCheckHighlighter"]
