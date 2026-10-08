# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, abstract_syntax_tree.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, immutable nodes;
# 2026-10-08: every function documented)
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


# A node stands on one line, most of the time: one shared set per line number instead
# of one set per node.
_SINGLE_LINES: dict[int, frozenset[int]] = {}


class Node:
    """A node of a syntax tree: a label, its children, and the source lines it spans.

    Attributes:
        label: What the node is: an operator, a statement kind, a name, a constant.
        children: Its children, in order.
        lines: The source lines this node itself stands on, without its children's.
    """

    __slots__ = ("_hash", "_size", "children", "label", "lines")

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
        found = frozenset(lines)
        if len(found) == 1:
            (line,) = found
            found = _SINGLE_LINES.setdefault(line, found)
        self.lines = found
        self._hash = hash((self.label, self.children))
        self._size: float | None = None

    @override
    def __eq__(self, other: object) -> bool:
        """Compare two trees by their labels and children, not by their lines.

        The hashes are compared first: two different trees rarely share one, and that
        spares walking them. A variable is never equal to a node.

        Args:
            other: Any object.

        Returns:
            Whether `other` is a node with the same label and equal children.
        """
        if self is other:
            return True
        if isinstance(other, Variable) or not isinstance(other, Node):
            return False
        return (
            self._hash == other._hash
            and self.label == other.label
            and self.children == other.children
        )

    @override
    def __hash__(self) -> int:
        """Hash the tree by its label and children, as `__eq__` compares it.

        Returns:
            The hash computed when the node was built.
        """
        return self._hash

    @override
    def __repr__(self) -> str:
        """Write the tree as a term, such as `Assign(Name(x), 1)`.

        Returns:
            The label of a leaf; otherwise the label and its children in parentheses.
        """
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
        """The source lines spanned by the node and all its descendants.

        Computed on each call: a statement keeps its own (see `Statement`). Kept on
        every node, these sets made most of the memory of a large run.
        """
        lines: set[int] = set()
        stack: list[Node] = [self]
        while stack:
            node = stack.pop()
            lines.update(node.lines)
            stack.extend(node.children)
        return frozenset(lines)


class Variable(Node):
    """A hole in a pattern: the place where two trees differ.

    A variable equals itself only. Its name is for display.
    """

    __slots__ = ()

    _COUNTER: Final = itertools.count(1)

    def __init__(self) -> None:
        """Make a new variable, distinct from every other."""
        super().__init__(f"X{next(Variable._COUNTER)}")

    @override
    def __eq__(self, other: object) -> bool:
        """Compare by identity: each variable is a hole of its own.

        Args:
            other: Any object.

        Returns:
            Whether `other` is this very variable.
        """
        return self is other

    @override
    def __hash__(self) -> int:
        """Hash by identity, as `__eq__` compares.

        Returns:
            The identity of the variable.
        """
        return id(self)
