# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every construct of recent Python is read, and its copies are found."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from clonedigger.detection import Settings, find_clones
from clonedigger.python_frontend import read_source
from clonedigger.report import Span

if TYPE_CHECKING:
    from clonedigger.python_frontend import SourceFile
    from clonedigger.tree import Node

PROBE = Path(__file__).parent / "samples" / "syntax_probe.py"

# The constructs Python 3.15 adds sit in a probe of their own: an earlier release
# raises SyntaxError on the file instead of reading it.
PROBE_3_15 = Path(__file__).parent / "samples" / "syntax_probe_3_15.py"
NEEDS_3_15 = pytest.mark.skipif(
    sys.version_info < (3, 15), reason="the probe is written in the syntax of Python 3.15"
)

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

# What each construct new in Python 3.15 becomes once read: the label of a node and the
# label of a child it holds. Unpacking in a comprehension (PEP 798) puts a `Starred`
# where the element of the comprehension stood; its `**` form gives a dict comprehension
# a key with no value, which ast leaves None. A literal pattern may now carry a unary
# plus, and the probe holds no other one. A lazy import (PEP 810) is still an import,
# which the front end leaves out, so it brings no label of its own.
CONSTRUCTS_3_15 = [
    ("unpacking in a list comprehension", {("ListComp", "Starred")}),
    ("unpacking in a set comprehension", {("SetComp", "Starred")}),
    ("unpacking in a generator expression", {("GeneratorExp", "Starred")}),
    ("unpacking in a dict comprehension", {("DictComp", "None")}),
    ("a unary plus in a literal pattern", {("MatchValue", "UnaryOp"), ("UnaryOp", "UAdd")}),
]


def labels(node: Node) -> set[str]:
    """Collect every label of a tree.

    Args:
        node: The tree.

    Returns:
        The labels of the node and of all its descendants.
    """
    return {node.label}.union(*(labels(child) for child in node.children))


def label_pairs(node: Node) -> set[tuple[str, str]]:
    """Collect every pair of a label and the label of one of its children.

    Args:
        node: The tree.

    Returns:
        The label of each node of the tree paired with the label of each of its children.
    """
    own = {(node.label, child.label) for child in node.children}
    return own.union(*(label_pairs(child) for child in node.children))


def probe_source(path: Path) -> SourceFile:
    """Read a probe, the same way on every system.

    Args:
        path: The probe.

    Returns:
        The file as the front end reads it.
    """
    return read_source(path, path.read_text(encoding="utf-8"))


def probe_trees(path: Path) -> list[Node]:
    """Read a probe into the trees of its statements.

    Args:
        path: The probe.

    Returns:
        The tree of every statement of every sequence of the file.
    """
    source = probe_source(path)
    return [statement.tree for sequence in source.sequences for statement in sequence]


@pytest.mark.parametrize("construct", CONSTRUCTS)
def test_each_construct_is_read(construct: str) -> None:
    """The construct appears in the trees read from the probe."""
    found = set().union(*(labels(tree) for tree in probe_trees(PROBE)))
    assert construct in found


@NEEDS_3_15
@pytest.mark.parametrize(("construct", "expected"), CONSTRUCTS_3_15)
def test_each_construct_new_in_3_15_is_read(construct: str, expected: set[tuple[str, str]]) -> None:
    """The construct Python 3.15 adds appears in the trees read from its probe."""
    del construct
    found = set().union(*(label_pairs(tree) for tree in probe_trees(PROBE_3_15)))
    assert expected <= found


@NEEDS_3_15
def test_a_lazy_import_is_left_out_like_any_other_import() -> None:
    """The lazy imports of the 3.15 probe, its only imports, reach no tree."""
    found = set().union(*(labels(tree) for tree in probe_trees(PROBE_3_15)))
    assert not found & {"Import", "ImportFrom"}


@pytest.mark.parametrize(
    ("kind", "probe", "starts"),
    [
        ("generators", PROBE, {10, 20}),
        ("match statements", PROBE, {30, 47}),
        ("async code", PROBE, {64, 75}),
        pytest.param("comprehensions that unpack", PROBE_3_15, {14, 22}, marks=NEEDS_3_15),
        pytest.param("patterns with a unary plus", PROBE_3_15, {30, 39}, marks=NEEDS_3_15),
    ],
)
def test_copies_written_in_recent_syntax_are_found(
    kind: str, probe: Path, starts: set[int]
) -> None:
    """Code copied under another set of names is a clone, in whatever syntax it is written."""
    del kind
    clones = find_clones([probe_source(probe)], Settings(size_threshold=3, distance_threshold=10))
    assert starts in [{Span.of(c.first).start, Span.of(c.second).start} for c in clones]
