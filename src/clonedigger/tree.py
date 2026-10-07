# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, abstract_syntax_tree.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, immutable nodes)
# SPDX-License-Identifier: GPL-3.0-or-later

"""The syntax trees that Clone Digger compares.

A tree is a label and an ordered tuple of children. Two trees are equal when their
labels and their children are equal: where a node comes from, its line numbers, do
not take part. A `Variable` is the hole that anti-unification puts where two trees
differ; each one is distinct from every other node, whatever its name.

Nodes are immutable, so their hash, their size and the lines they cover are computed
once. In Clone Digger 1.1.0 a node was mutable and computed them on demand.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Final, override

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# What a variable adds to the size of a tree, against 1 for a name or a constant.
# Clone Digger 1.1.0 calls it free_variable_cost.
VARIABLE_COST: Final = 0.5


class Node:
    """A node of a syntax tree: a label, its children, and the source lines it spans."""

    __slots__ = ("_covered", "_hash", "_size", "children", "label", "lines")

    label: str
    children: tuple[Node, ...]
    lines: frozenset[int]

    def __init__(
        self, label: str, children: Iterable[Node] = (), lines: Iterable[int] = ()
    ) -> None:
        """Build a node.

        Args:
            label: What the node is: an operator, a statement kind, a name, a constant.
            children: Its children, in order.
            lines: The source lines this node itself stands on, without its children's.
        """
        self.label = label
        self.children = tuple(children)
        self.lines = frozenset(lines)
        self._hash = hash((self.label, self.children))
        self._size: float | None = None
        self._covered: frozenset[int] | None = None

    @override
    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if type(other) is not Node:
            return False
        return (
            self._hash == other._hash
            and self.label == other.label
            and self.children == other.children
        )

    @override
    def __hash__(self) -> int:
        return self._hash

    @override
    def __repr__(self) -> str:
        if not self.children:
            return self.label
        return f"{self.label}({', '.join(map(repr, self.children))})"

    @property
    def is_leaf(self) -> bool:
        """Whether the node has no children: a name, a constant, or a variable."""
        return not self.children

    def leaves(self) -> Iterator[Node]:
        """Yield the leaves of the tree, left to right, repeats included.

        Yields:
            Each leaf.
        """
        stack: list[Node] = [self]
        while stack:
            node = stack.pop()
            if node.is_leaf:
                yield node
            else:
                stack.extend(reversed(node.children))

    @property
    def size(self) -> float:
        """How much the tree weighs when two trees are compared.

        It counts the distinct leaves: 1 for each name or constant, `VARIABLE_COST`
        for each variable. A leaf that occurs twice counts once, as in Clone Digger
        1.1.0, where equal leaves were recorded in one set.
        """
        if self._size is None:
            self._size = sum(
                VARIABLE_COST if isinstance(leaf, Variable) else 1.0 for leaf in set(self.leaves())
            )
        return self._size

    @property
    def covered_lines(self) -> frozenset[int]:
        """The source lines spanned by the node and all its descendants."""
        if self._covered is None:
            self._covered = self.lines.union(*(child.covered_lines for child in self.children))
        return self._covered


class Variable(Node):
    """A hole in a pattern: the place where two trees differ.

    A variable equals itself only. Its name is for display.
    """

    __slots__ = ()

    _counter: Final = itertools.count(1)

    def __init__(self) -> None:
        """Make a new variable, distinct from every other."""
        super().__init__(f"X{next(Variable._counter)}")

    @override
    def __eq__(self, other: object) -> bool:
        return self is other

    @override
    def __hash__(self) -> int:
        return id(self)
