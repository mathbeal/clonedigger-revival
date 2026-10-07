# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The HTML page shows each clone side by side, its differences marked."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from clonedigger import __version__
from clonedigger.detection import find_clones
from clonedigger.html_report import as_html, highlight, source_text
from clonedigger.python_frontend import Statement, read_source
from clonedigger.tree import Node

INPUTS = Path(__file__).parent / "golden" / "inputs"


class _Tags(HTMLParser):
    """Collect the tags of a page, and check that each opened one is closed."""

    VOID = frozenset({"meta"})

    def __init__(self) -> None:
        super().__init__()
        self.open: list[str] = []
        self.seen: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.seen.append(tag)
        if tag not in self.VOID:
            self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.open.pop() == tag


def page() -> str:
    """Build the page of the recorded inputs.

    Returns:
        The HTML.
    """
    files = [
        read_source(Path("inputs") / path.name, path.read_text())
        for path in sorted(INPUTS.glob("*.py"))
    ]
    return as_html(find_clones(files), {file.path: file.lines for file in files})


def test_the_page_is_well_formed() -> None:
    """Every tag opened is closed, in order, and the page has one table per clone."""
    tags = _Tags()
    tags.feed(page())
    assert not tags.open
    assert tags.seen.count("table") == 1
    assert tags.seen[:2] == ["html", "head"]


def test_the_page_names_the_clone_and_both_copies() -> None:
    """The heading, the distance, the size and the two places are shown."""
    text = page()
    assert '<h2 id="clone-1">Clone 1</h2>' in text
    assert "<p>Distance 4, up to 6 lines.</p>" in text
    assert "prices.py:13-18</th>" in text
    assert "prices.py:2-7</th>" in text
    assert "1 clone found." in text
    assert f"Clone Digger {__version__}, by Peter Bulychev" in text
    assert "<mark>amount</mark>" in text


def test_an_empty_page_says_so() -> None:
    """With no clone, the page says none was found."""
    text = as_html([], {})
    assert "0 clones found." in text
    assert "<table>" not in text


def test_differences_are_marked_and_escaped() -> None:
    """Only what differs is marked, and markup in the code is escaped."""
    left, right = highlight("a < b and c", "a < d and c")
    assert left == "a &lt; <mark>b</mark> and c"
    assert right == "a &lt; <mark>d</mark> and c"
    assert highlight("same", "same") == ("same", "same")
    assert highlight("a b", "a") == ("a<mark> b</mark>", "a")
    assert highlight("amount = 0", "total = 0") == (
        "<mark>amount</mark> = 0",
        "<mark>total</mark> = 0",
    )


def test_source_is_cut_to_the_statement_and_dedented() -> None:
    """A statement shows its own lines, without the indentation they share."""
    lines = ["def f():", "    if x:", "        y = 1", "", "    return y"]
    statement = Statement(Node("If", lines={2, 3}), Path("a.py"))
    assert source_text(statement, lines) == "if x:\n    y = 1"
    blank = Statement(Node("Pass", lines={4}), Path("a.py"))
    assert not source_text(blank, lines)


def test_long_texts_are_compared_word_by_word_too() -> None:
    """Common words are not set aside as noise, however long the text."""
    left, right = highlight("x " * 120 + "p " + "x " * 120, "x " * 120 + "q " + "x " * 120)
    assert left == "x " * 120 + "<mark>p</mark> " + "x " * 120
    assert right == "x " * 120 + "<mark>q</mark> " + "x " * 120


def test_clones_follow_one_another() -> None:
    """Two clones make two tables, one after the other."""
    body = "def {0}(a):\n    b = a + 1\n    c = b * 2\n    d = c - 3\n    e = d / 4\n    return e\n"
    text = "".join(body.format(name) for name in ("f", "g")) + "\n"
    other = "".join(body.replace("+", "-").format(name) for name in ("h", "k"))
    files = [read_source(Path("a.py"), text), read_source(Path("b.py"), other)]
    sources = {file.path: file.lines for file in files}
    clones = find_clones(files)
    assert len(clones) >= 2
    assert as_html(clones, sources).count("</table>\n<h2") == len(clones) - 1


def test_the_page_is_written_as_recorded() -> None:
    """Every text and tag of the page is the recorded one.

    After a deliberate change, regenerate tests/data/report.html from page(), with
    the tool's version written <version>.
    """
    expected = (Path(__file__).parent / "data" / "report.html").read_text()
    assert page().replace(__version__, "<version>") == expected
