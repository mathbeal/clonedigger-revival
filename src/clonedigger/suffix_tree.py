# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, suffix_tree.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, typed, generic;
# 2026-10-08: every function documented)
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
    """A place in a suffix of a string, and the code just before that suffix.

    The suffix is not copied: it is `string[start:]`, read when a run is reported.
    Copying every suffix made the memory grow with the square of a string's length.

    Attributes:
        string: The whole string the suffix belongs to.
        start: Where the suffix starts in it.
        position: How far into the suffix this place is.
        previous: The code of the element just before the suffix; None at the start of
            the string.
    """

    string: Sequence[T]
    start: int
    position: int
    previous: Hashable | None

    def run(self, length: int) -> Sequence[T]:
        """Return the run made of the first elements of the suffix.

        Args:
            length: How many.

        Returns:
            Them, as a slice of the string.
        """
        return self.string[self.start : self.start + length]


@dataclass(slots=True)
class _TrieNode[T]:
    """A node of the trie: one code further down every suffix that passes it.

    Attributes:
        children: The next node for each code that follows.
        passing: The places of the suffixes that go on below this node.
        ending: The places of the suffixes that end here.
    """

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
            self._add_suffix(string, start, previous)

    def _add_suffix(self, string: Sequence[T], start: int, previous: Hashable | None) -> None:
        """Walk one suffix down the trie, recording its place in every node it passes.

        Args:
            string: The string.
            start: Where the suffix starts.
            previous: The code of the element just before it; None at the start.
        """
        node = self._root
        for position in range(len(string) - start):
            node.passing.append(_Position(string, start, position, previous))
            node = node.children.setdefault(self._code(string[start + position]), _TrieNode())
        node.ending.append(_Position(string, start, len(string) - start, previous))

    def iter_best_max_substrings(
        self,
        threshold: float,
        weight: Callable[[Hashable], float],
        size: Callable[[Sequence[T]], float],
    ) -> Iterator[tuple[Sequence[T], Sequence[T]]]:
        """Find the pairs of maximal repeated runs that are heavy enough, one at a time.

        On a large code base the pairs number in the millions: yielding them one at a
        time lets the caller handle each and forget it.

        Args:
            threshold: The weight a run must reach, summed along the path from the root.
            weight: The weight of one element, from its code.
            size: The size of a candidate run; a pair is kept when one side reaches
                `threshold`.

        Yields:
            Pairs of runs, as slices of the strings that were added.
        """
        # The same prefix of a string is weighed again for every string it meets: its
        # size is kept, keyed by the string, which the tree keeps alive, and the length.
        sizes: dict[tuple[int, int, int], float] = {}

        def heavy(place: _Position[T], length: int) -> bool:
            """Tell whether a run is large enough, weighing each run once.

            Args:
                place: Where the run starts.
                length: How many elements it holds.

            Returns:
                Whether its size reaches the threshold.
            """
            key = (id(place.string), place.start, length)
            if key not in sizes:
                sizes[key] = size(place.run(length))
            return sizes[key] >= threshold

        def find_from(
            node: _TrieNode[T], remaining: float
        ) -> Iterator[tuple[Sequence[T], Sequence[T]]]:
            """Report the pairs that meet at a node and below it, once heavy enough.

            Args:
                node: The node of the trie.
                remaining: The weight still missing along the path from the root.

            Yields:
                The pairs of left-diverse runs that meet there, or deeper.
            """
            if remaining <= 0:
                for one, two, back in _comparisons(node):
                    # A run is left-diverse when it starts a string, or follows different
                    # elements.
                    diverse = one.previous is None or one.previous != two.previous
                    first, second = one.position - back, two.position - back
                    if diverse and first > 0 and (heavy(one, first) or heavy(two, second)):
                        yield one.run(first), two.run(second)
            for code, child in node.children.items():
                yield from find_from(child, remaining - weight(code))

        yield from find_from(self._root, threshold)
