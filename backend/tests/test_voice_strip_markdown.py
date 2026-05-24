"""Unit tests for the markdown stripper used by the TTS path.

The chat renders agent responses as markdown, but Google TTS would read
characters like `*` and `#` aloud. `_strip_markdown_for_tts` turns the
markdown back into plain prose before synthesis.
"""

from __future__ import annotations

import pytest

from app.voice import _strip_markdown_for_tts


@pytest.mark.parametrize(
    "markdown, expected",
    [
        # bold
        ("Got it **Omar Hassan** as the subject.", "Got it Omar Hassan as the subject."),
        ("__bold__ word", "bold word"),
        # italic
        ("That's *important* to know.", "That's important to know."),
        ("an _italic_ word", "an italic word"),
        # nested bold + italic
        ("**bold *with* italic**", "bold with italic"),
        # inline code
        ("Use `update_draft` to set it.", "Use update_draft to set it."),
        # fenced code block
        ("Pre\n```\nblock body\n```\nPost", "Pre\n\nPost"),
        # headings
        ("# Top\nbody", "Top\nbody"),
        ("### Smaller\nbody", "Smaller\nbody"),
        # links — keep label, drop URL
        ("See [the docs](https://example.com).", "See the docs."),
        # blockquote
        ("> a quoted line\nrest", "a quoted line\nrest"),
        # bullets and numbered list markers
        ("- first\n- second", "first\nsecond"),
        ("1. one\n2. two", "one\ntwo"),
        # plain text untouched
        ("just plain prose.", "just plain prose."),
        # empty input survives
        ("", ""),
    ],
)
def test_strip_markdown_for_tts(markdown: str, expected: str) -> None:
    assert _strip_markdown_for_tts(markdown) == expected
