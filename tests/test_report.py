# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reports locate both copies of every clone, largest first."""

from __future__ import annotations

from pathlib import Path

from clonedigger.detection import Clone
from clonedigger.python_frontend import Statement
from clonedigger.report import as_json, as_text, findings
from clonedigger.tree import Node


def run(path: str, lines: range) -> tuple[Statement, ...]:
    """Build a run of one-line statements.

    Returns:
        One statement per line.
    """
    return tuple(Statement(Node("Pass", lines={line}), Path(path)) for line in lines)


SMALL = Clone(run("a.py", range(1, 6)), run("b.py", range(10, 15)), 2)
LARGE = Clone(run("c.py", range(1, 9)), run("d.py", range(20, 28)), 1)


def test_findings_come_largest_first_with_both_copies() -> None:
    """The longest clone comes first, and each finding names both copies."""
    first, second = findings([SMALL, LARGE])
    assert (str(first.first), str(first.second)) == ("c.py:1-8", "d.py:20-27")
    assert (str(second.first), str(second.second)) == ("a.py:1-5", "b.py:10-14")
    assert first.distance == 1


def test_text_has_one_line_per_clone_then_a_count() -> None:
    """Each clone on its own line, then how many were found."""
    assert as_text([SMALL, LARGE]).split("\n") == [
        "c.py:1-8  ~  d.py:20-27  (distance 1)",
        "a.py:1-5  ~  b.py:10-14  (distance 2)",
        "2 clones found.",
    ]


def test_json_is_indented_by_two() -> None:
    """The JSON is an array of findings, indented by two spaces."""
    expected = """[
  {
    "first": {
      "path": "a.py",
      "start": 1,
      "end": 5
    },
    "second": {
      "path": "b.py",
      "start": 10,
      "end": 14
    },
    "distance": 2
  }
]"""
    assert as_json([SMALL]) == expected
