# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, html_report.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: rewritten, one self-contained page)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write the clones as one HTML page: each clone side by side, its differences marked.

As in Clone Digger 1.1.0, the two copies of a clone are shown statement against
statement, and what differs between them, character by character, is highlighted.
The page needs nothing else: no script, no external stylesheet, no font.
"""

from __future__ import annotations

import difflib
import html
import re
from typing import TYPE_CHECKING, Final

from clonedigger import __version__
from clonedigger.report import Span, largest_first

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from clonedigger.detection import Clone
    from clonedigger.python_frontend import Statement

STYLE: Final = """
:root { color-scheme: light dark; --mark: #ffd8d8; --line: #888; }
@media (prefers-color-scheme: dark) { :root { --mark: #6b2020; } }
body { font-family: system-ui, sans-serif; margin: 1.5rem; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; margin-bottom: 2rem; }
th, td { border: 1px solid var(--line); padding: 0.25rem 0.5rem; vertical-align: top; }
pre { margin: 0; white-space: pre-wrap; font-family: ui-monospace, monospace; }
mark { background: var(--mark); color: inherit; }
"""


def source_text(statement: Statement, lines: Sequence[str]) -> str:
    """Copy the source of a statement, from its first line to its last.

    Args:
        statement: The statement.
        lines: The lines of its file, the first one numbered 1.

    Returns:
        Its lines, joined, with the indentation they have in common removed.
    """
    covered = statement.covered_lines
    chunk = lines[min(covered) - 1 : max(covered)]
    indents = [len(line) - len(line.lstrip()) for line in chunk if line.strip()]
    if not indents:
        return ""
    margin = min(indents)
    return "\n".join(line[margin:] for line in chunk)


# A word, a run of spaces, or any other single character: the units compared.
TOKEN: Final = re.compile(r"\w+|\s+|.", re.DOTALL)


def highlight(first: str, second: str) -> tuple[str, str]:
    """Escape two texts for HTML, and mark the words that differ between them.

    Clone Digger 1.1.0 compared characters, which marks `amount` against `total` as
    "a" kept and the rest changed. Comparing words, spaces and symbols marks whole
    names, as a reader sees them.

    Args:
        first: One text.
        second: The other.

    Returns:
        Both, escaped, with the parts that differ wrapped in `<mark>`.
    """
    tokens = (TOKEN.findall(first), TOKEN.findall(second))
    # Without autojunk: in a long statement, common words must still anchor the match.
    matcher = difflib.SequenceMatcher(
        None, *tokens, autojunk=False
    )  # pragma: no mutate - None is False
    marked: tuple[list[str], list[str]] = ([], [])
    for tag, start_1, end_1, start_2, end_2 in matcher.get_opcodes():
        parts = ("".join(tokens[0][start_1:end_1]), "".join(tokens[1][start_2:end_2]))
        for out, text in zip(marked, parts, strict=True):  # pragma: no mutate - two and two
            escaped = html.escape(text)
            out.append(escaped if tag == "equal" or not text else f"<mark>{escaped}</mark>")
    return "".join(marked[0]), "".join(marked[1])


def _clone_table(number: int, clone: Clone, sources: Mapping[Path, Sequence[str]]) -> str:
    first, second = Span.of(clone.first), Span.of(clone.second)
    rows = []
    # Both copies of a clone have as many statements.
    for one, other in zip(clone.first, clone.second, strict=True):  # pragma: no mutate
        left, right = highlight(
            source_text(one, sources[one.path]), source_text(other, sources[other.path])
        )
        rows.append(f"<tr><td><pre>{left}</pre></td><td><pre>{right}</pre></td></tr>")
    size = max(first.end - first.start, second.end - second.start) + 1
    return (
        f'<h2 id="clone-{number}">Clone {number}</h2>\n'
        f"<p>Distance {clone.distance:g}, up to {size} lines.</p>\n"
        f"<table>\n<tr><th>{html.escape(str(first))}</th>"
        f"<th>{html.escape(str(second))}</th></tr>\n" + "\n".join(rows) + "\n</table>"
    )


def as_html(clones: Sequence[Clone], sources: Mapping[Path, Sequence[str]]) -> str:
    """Write the clones as one HTML page, largest first.

    Args:
        clones: The clones found.
        sources: The lines of every file a clone comes from.

    Returns:
        The page.
    """
    tables = "\n".join(
        _clone_table(number, clone, sources)
        for number, clone in enumerate(largest_first(clones), start=1)
    )
    count = f"{len(clones)} clone{'' if len(clones) == 1 else 's'} found."
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Clone Digger report</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        "<h1>Clone Digger report</h1>\n"
        f"<p>{count} Clone Digger {html.escape(__version__)}, by Peter Bulychev, "
        "ported to Python 3.</p>\n"
        f"{tables}\n</body>\n</html>\n"
    )
