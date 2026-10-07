# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Trees compare by shape, and measure themselves as Clone Digger 1.1.0 did."""

from __future__ import annotations

from clonedigger import VARIABLE_COST, Node, Variable


def test_equality_ignores_lines() -> None:
    """Two trees of the same shape are equal wherever they come from."""
    assert Node("Add", (Node("a"),), lines={1}) == Node("Add", (Node("a"),), lines={9})
    assert hash(Node("a", lines={1})) == hash(Node("a", lines={2}))


def test_equality_needs_same_label_and_children() -> None:
    """A different label or a different child makes a different tree."""
    assert Node("Add", (Node("a"),)) != Node("Sub", (Node("a"),))
    assert Node("Add", (Node("a"),)) != Node("Add", (Node("b"),))
    assert Node("a") != "a"


def test_a_variable_equals_only_itself() -> None:
    """Variables never match each other, nor a node that has their name."""
    first, second = Variable(), Variable()
    same = first
    assert first == same
    assert first != second
    assert first != Node(first.label)
    assert Node(first.label) != first
    assert hash(first) != hash(second)


def test_size_counts_distinct_leaves() -> None:
    """A repeated leaf counts once; a variable counts VARIABLE_COST."""
    assert Node("Add", (Node("a"), Node("a"))).size == 1
    assert Node("Add", (Node("a"), Node("b"))).size == 2
    assert Node("Add", (Variable(), Node("b"))).size == 1 + VARIABLE_COST


def test_covered_lines_include_descendants() -> None:
    """A node covers its own lines and those of everything below it."""
    node = Node("If", (Node("x", lines={2}), Node("Return", (Node("y", lines={3}),))), lines={1})
    assert node.covered_lines == {1, 2, 3}


def test_leaves_are_in_order() -> None:
    """Leaves come left to right, repeats included."""
    node = Node("Call", (Node("f"), Node("Add", (Node("a"), Node("a")))))
    assert [leaf.label for leaf in node.leaves()] == ["f", "a", "a"]


def test_repr_reads_like_the_tree() -> None:
    """A tree prints as its label and its children."""
    assert repr(Node("Add", (Node("a"), Node("1")))) == "Add(a, 1)"


def test_measures_are_computed_once() -> None:
    """Asking twice gives the same answer from the stored value."""
    node = Node("Add", (Node("a", lines={1}), Node("b", lines={2})))
    assert node.covered_lines is node.covered_lines
    assert node.size == node.size == 2


def test_different_trees_hash_apart() -> None:
    """Different labels or children give different hashes, so dictionaries stay fast."""
    assert len({hash(Node("a")), hash(Node("b")), hash(Node("Add", (Node("a"),)))}) == 3


def test_variables_are_named_for_display() -> None:
    """A variable shows as X followed by a number."""
    assert Variable().label.startswith("X")
