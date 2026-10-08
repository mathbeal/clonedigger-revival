# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every construct of recent Python is read, and its copies are found."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from clonedigger.detection import Settings, find_clones
from clonedigger.python_frontend import read_source
from clonedigger.report import Span

if TYPE_CHECKING:
    from clonedigger.tree import Node

PROBE = Path(__file__).parent / "samples" / "syntax_probe.py"

CONSTRUCTS = [
    "Yield",
    "YieldFrom",
    "Match",
    "match_case",
    "MatchMapping",
    "MatchSequence",
    "MatchStar",
    "MatchClass",
    "MatchOr",
    "MatchAs",
    "AsyncWith",
    "AsyncFor",
    "Await",
    "NamedExpr",
    "TryStar",
    "TypeAlias",
    "JoinedStr",
    "FormattedValue",
    "Lambda",
    "ListComp",
    "DictComp",
    "Starred",
]


def labels(node: Node) -> set[str]:
    """Collect every label of a tree.

    Args:
        node: The tree.

    Returns:
        The labels of the node and of all its descendants.
    """
    return {node.label}.union(*(labels(child) for child in node.children))


@pytest.mark.parametrize("construct", CONSTRUCTS)
def test_each_construct_is_read(construct: str) -> None:
    """The construct appears in the trees read from the probe."""
    source = read_source(PROBE, PROBE.read_text())
    found = set().union(*(labels(s.tree) for seq in source.sequences for s in seq))
    assert construct in found


@pytest.mark.parametrize(
    ("kind", "starts"),
    [("generators", {10, 20}), ("match statements", {30, 47}), ("async code", {64, 75})],
)
def test_copies_written_in_recent_syntax_are_found(kind: str, starts: set[int]) -> None:
    """Generators, match statements and async code copied under other names are clones."""
    del kind
    clones = find_clones(
        [read_source(PROBE, PROBE.read_text())], Settings(size_threshold=3, distance_threshold=10)
    )
    assert starts in [{Span.of(c.first).start, Span.of(c.second).start} for c in clones]
