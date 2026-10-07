# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, suffix_tree.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, typed, generic)
# SPDX-License-Identifier: GPL-3.0-or-later

"""A suffix trie, to find the runs of elements that occur in two places.

Clone Digger labels every statement with the cluster it belongs to, so that a
sequence of statements reads as a string of labels. Two places where the same run of
labels occurs are candidate clones. This structure finds the longest such runs, those
that cannot be extended to the left (they are "left-diverse") and whose weight
reaches a threshold.

It stores every suffix of every string in a trie, which is quadratic in the length
of a string, as in Clone Digger 1.1.0. The statement sequences it is given are short.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class _Position[T]:
    """A place in a string: the string, how far into it, and the code just before."""

    string: Sequence[T]
    position: int
    previous: Hashable | None


@dataclass(slots=True)
class _TrieNode[T]:
    children: dict[Hashable, _TrieNode[T]] = field(default_factory=dict)
    passing: list[_Position[T]] = field(default_factory=list)
    ending: list[_Position[T]] = field(default_factory=list)


def _comparisons[T](node: _TrieNode[T]) -> Iterator[tuple[_Position[T], _Position[T], int]]:
    """List the pairs of places a node can join, and how far back each run ends.

    Three kinds, in the order of Clone Digger 1.1.0: a string ending here against one
    passing through, two strings ending here, and two strings that part ways into
    different children, one element further down.

    Args:
        node: The node of the trie where the runs meet.

    Yields:
        Two positions, and how many elements to step back from them.
    """
    for one in node.ending:
        # Clone Digger 1.1.0 skipped a pair here when both strings had equal contents.
        # That never happens: at a given depth, a string that ends is shorter than one
        # that passes through, so the test is left out.
        for two in node.passing:
            yield one, two, 0
    for i, one in enumerate(node.ending):
        for two in node.ending[:i]:
            yield one, two, 0
    branches = list(node.children.values())
    for i, branch in enumerate(branches):
        for other in branches[:i]:
            for one in branch.passing + branch.ending:
                for two in other.passing + other.ending:
                    yield one, two, 1


class SuffixTree[T]:
    """All the suffixes of a set of strings, keyed by the code of each element."""

    def __init__(self, code: Callable[[T], Hashable]) -> None:
        """Make an empty tree.

        Args:
            code: What identifies an element: two elements with the same code match.
        """
        self._root: _TrieNode[T] = _TrieNode()
        self._code = code

    def add(self, string: Sequence[T]) -> None:
        """Add every suffix of a string.

        Args:
            string: The elements, in order.
        """
        for start in range(len(string)):
            previous = None if start == 0 else self._code(string[start - 1])
            self._add_suffix(string[start:], previous)

    def _add_suffix(self, suffix: Sequence[T], previous: Hashable | None) -> None:
        node = self._root
        for position, element in enumerate(suffix):
            node.passing.append(_Position(suffix, position, previous))
            node = node.children.setdefault(self._code(element), _TrieNode())
        node.ending.append(_Position(suffix, len(suffix), previous))

    def best_max_substrings(
        self,
        threshold: float,
        weight: Callable[[Hashable], float],
        size: Callable[[Sequence[T]], float],
    ) -> list[tuple[Sequence[T], Sequence[T]]]:
        """Find the pairs of maximal repeated runs that are heavy enough.

        Args:
            threshold: The weight a run must reach, summed along the path from the root.
            weight: The weight of one element, from its code.
            size: The size of a candidate run; a pair is kept when one side reaches
                `threshold`.

        Returns:
            Pairs of runs, as slices of the strings that were added.
        """
        found: list[tuple[Sequence[T], Sequence[T]]] = []
        # The same prefix of a string is weighed again for every string it meets: its
        # size is kept, keyed by the string, which the tree keeps alive, and the length.
        sizes: dict[tuple[int, int], float] = {}

        def heavy(string: Sequence[T], length: int) -> bool:
            key = (id(string), length)
            if key not in sizes:
                sizes[key] = size(string[:length])
            return sizes[key] >= threshold

        def keep_if_left_diverse(one: _Position[T], two: _Position[T], back: int) -> None:
            # A run is left-diverse when it starts a string, or follows different elements.
            diverse = one.previous is None or one.previous != two.previous
            if diverse and one.position > back:
                first, second = one.position - back, two.position - back
                if heavy(one.string, first) or heavy(two.string, second):
                    found.append((one.string[:first], two.string[:second]))

        def find_from(node: _TrieNode[T], remaining: float) -> None:
            if remaining <= 0:
                for one, two, back in _comparisons(node):
                    keep_if_left_diverse(one, two, back)
            for code, child in node.children.items():
                find_from(child, remaining - weight(code))

        find_from(self._root, threshold)
        return found
