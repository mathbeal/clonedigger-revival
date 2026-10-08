# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, anti_unification.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, typed, one pass;
# 2026-10-08: every function documented)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Anti-unification: the most specific pattern that two trees are both instances of.

The algorithm is the one of Clone Digger, described by Peter Bulychev and Marius
Minea in "Duplicate Code Detection Using Anti-Unification" (SYRCoSE 2008). The two
trees are walked together from the root:

1. equal subtrees are kept as they are;
2. nodes with the same label and the same number of children are kept, and their
   children are anti-unified in turn;
3. anything else becomes a variable, and each side records what the variable stands
   for.

The same pair of differing subtrees always gets the same variable: `a + a` and
`b + b` give `X + X`, not `X + Y`. Clone Digger 1.1.0 merged such variables while
going back up the tree; here a table of the pairs already seen does it in one pass,
with the same result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import starmap
from typing import TYPE_CHECKING

from clonedigger.tree import VARIABLE_COST, Node, Variable

if TYPE_CHECKING:
    from collections.abc import Mapping


def substitution_size(substitution: Mapping[Variable, Node]) -> float:
    """How much a substitution weighs: what it replaces, less the cost of its holes.

    Args:
        substitution: What each variable stands for, on one side.

    Returns:
        The sum, over the variables, of the size of their subtree less `VARIABLE_COST`.
    """
    return sum(tree.size - VARIABLE_COST for tree in substitution.values())


def substitute(pattern: Node, substitution: Mapping[Variable, Node]) -> Node:
    """Fill the holes of a pattern.

    Args:
        pattern: A tree that may contain variables.
        substitution: What some of its variables stand for.

    Returns:
        The pattern with each of those variables replaced by its subtree.
    """
    if isinstance(pattern, Variable):
        return substitution.get(pattern, pattern)
    if pattern.is_leaf:
        return pattern
    return Node(
        pattern.label,
        (substitute(child, substitution) for child in pattern.children),
        pattern.lines,
    )


@dataclass(frozen=True, slots=True)
class AntiUnification:
    """The result of anti-unifying two trees.

    Attributes:
        pattern: The most specific tree both are instances of, with variables.
        left: What each variable stands for in the first tree.
        right: What each variable stands for in the second tree.
    """

    pattern: Node
    left: dict[Variable, Node] = field(default_factory=dict)
    right: dict[Variable, Node] = field(default_factory=dict)

    @property
    def variables(self) -> int:
        """How many places the two trees differ in."""
        return len(self.left)

    @property
    def left_size(self) -> float:
        """The weight of what the first tree puts in the holes."""
        return substitution_size(self.left)

    @property
    def right_size(self) -> float:
        """The weight of what the second tree puts in the holes."""
        return substitution_size(self.right)

    @property
    def distance(self) -> float:
        """How different the two trees are: 0 when they are equal."""
        return self.left_size + self.right_size


def anti_unify(first: Node, second: Node, *, share_variables: bool = True) -> AntiUnification:
    """Find the most specific pattern of two trees, and what each puts in its holes.

    Args:
        first: A tree.
        second: Another tree.
        share_variables: Give the same variable to the same pair of differing
            subtrees. Clone Digger 1.1.0 calls the opposite `ignore_parametrization`.

    Returns:
        The pattern and the two substitutions, which turn it back into each tree.
    """
    left: dict[Variable, Node] = {}
    right: dict[Variable, Node] = {}
    seen: dict[tuple[Node, Node], Variable] = {}

    def hole(one: Node, other: Node) -> Variable:
        """Give a pair of differing subtrees its variable, and record what it stands for.

        Args:
            one: The subtree of the first tree.
            other: The subtree of the second.

        Returns:
            The variable of that pair: the one it already has, when variables are shared.
        """
        if share_variables and (one, other) in seen:
            return seen[one, other]
        variable = Variable()
        left[variable] = one
        right[variable] = other
        seen[one, other] = variable
        return variable

    def walk(one: Node, other: Node) -> Node:
        """Anti-unify two subtrees, from their roots down.

        Args:
            one: A subtree of the first tree.
            other: The subtree at the same place in the second.

        Returns:
            Their pattern: kept where they agree, a variable where they differ.
        """
        if one == other:
            return one
        if one.label != other.label or len(one.children) != len(other.children):
            return hole(one, other)
        # Equal lengths were checked just above: strict only guards the invariant, so
        # mutating it cannot change a result.
        pairs = zip(one.children, other.children, strict=True)  # pragma: no mutate
        return Node(one.label, starmap(walk, pairs), one.lines)

    return AntiUnification(walk(first, second), left, right)


def difference(first: Node, second: Node, limit: float = float("inf")) -> tuple[float, float]:
    """Weigh what anti-unifying two trees would put in its holes, without building it.

    The clustering steps only need these two numbers, and compare a statement with
    every cluster of its bucket: building the pattern and the variables there would be
    wasted work. The walk is the one of `anti_unify`, with variables shared.

    Args:
        first: A tree.
        second: Another tree.
        limit: Stop as soon as the two sizes add up to this much or more: the caller
            only wants to know whether the trees are closer than that.

    Returns:
        The `left_size` and the `right_size` of `anti_unify(first, second)`, or, once
        their sum reaches `limit`, the sizes found so far.
    """
    seen: set[tuple[Node, Node]] = set()
    left = right = 0.0
    stack = [(first, second)]
    while stack:
        one, other = stack.pop()
        if one == other:
            continue
        if one.label != other.label or len(one.children) != len(other.children):
            if (one, other) not in seen:
                seen.add((one, other))
                left += one.size - VARIABLE_COST
                right += other.size - VARIABLE_COST
                if left + right >= limit:
                    break
            continue
        stack.extend(zip(one.children, other.children, strict=True))  # pragma: no mutate
    return left, right


class Cluster:
    """Statements of the same shape, with the pattern they all fit.

    Clone Digger puts each statement in the cluster that it changes least; a
    statement that would change every cluster too much starts its own.
    """

    def __init__(self, tree: Node | None = None) -> None:
        """Start a cluster.

        Args:
            tree: Its first statement, which is also its first pattern. Without one,
                the cluster is only a label for statements added with
                `add_without_unification`.
        """
        self.trees: list[Node] = []
        self.pattern: Node | None = tree
        self.max_covered_lines = 0
        if tree is not None:
            self.add_without_unification(tree)

    def __len__(self) -> int:
        """Count the statements of the cluster.

        Returns:
            How many statements the cluster holds.
        """
        return len(self.trees)

    def add_cost(self, tree: Node, limit: float = float("inf")) -> float:
        """What adding a statement would cost: every member's share of the new holes.

        Args:
            tree: The statement to add.
            limit: The caller only needs the cost if it is below this: the weighing
                stops once it is sure to reach it.

        Returns:
            The size of what the pattern would lose, once for each member already in
            the cluster, plus the size of what the new statement brings; when that is
            `limit` or more, a value of at least `limit`.

        Raises:
            ValueError: If the cluster has no pattern.
        """
        if self.pattern is None:
            msg = "a cluster made without a tree has no pattern to compare with"
            raise ValueError(msg)
        # The cost is at least left + right, so stopping the weighing at the limit is safe.
        left, right = difference(self.pattern, tree, limit)  # pragma: no mutate - time only
        return len(self) * left + right

    def unify(self, tree: Node) -> None:
        """Add a statement, and widen the pattern to fit it.

        Args:
            tree: The statement to add.

        Raises:
            ValueError: If the cluster has no pattern.
        """
        if self.pattern is None:
            msg = "a cluster made without a tree has no pattern to widen"
            raise ValueError(msg)
        self.pattern = anti_unify(self.pattern, tree).pattern
        # As in Clone Digger 1.1.0, only add_without_unification updates the largest
        # number of covered lines: the marking pass that follows adds statements again.
        self.trees.append(tree)

    def add_without_unification(self, tree: Node) -> None:
        """Add a statement and leave the pattern as it is.

        Args:
            tree: The statement to add.
        """
        self.trees.append(tree)
        self.max_covered_lines = max(self.max_covered_lines, len(tree.covered_lines))
