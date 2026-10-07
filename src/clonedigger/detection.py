# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, clone_detection_algorithm.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, split in steps)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Find the clones in a set of files: the pipeline of Clone Digger, step by step.

1. Keep the statement sequences that span enough lines.
2. Put statements of the same rough shape in the same bucket (`dcup_hash`).
3. In each bucket, gather statements into clusters around a common pattern.
4. Mark every statement with its cluster: a sequence becomes a string of marks.
5. Leave out long runs of statements that all have the same mark.
6. Find, with a suffix tree, the longest runs of marks that occur twice.
7. Keep the pairs whose anti-unification distance is small enough.
8. Drop a clone that lies inside a larger one.

The thresholds keep their meaning and their default values. They are passed as
`Settings` instead of the module-level globals of Clone Digger 1.1.0.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING

from clonedigger.anti_unification import Cluster, anti_unify
from clonedigger.suffix_tree import SuffixTree
from clonedigger.tree import Node

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Sequence

    from clonedigger.python_frontend import SourceFile, Statement

# Clone Digger 1.1.0 left out a run of statements once more than this many followed
# the first with the same mark: such runs (long lists of similar assignments) match
# each other everywhere and say nothing.
MAX_EQUAL_MARKS = 10


@dataclass(frozen=True)
class Settings:
    """The thresholds of the detection, with the defaults of Clone Digger 1.1.0.

    Attributes:
        size_threshold: The fewest source lines a clone must span, on both sides.
        distance_threshold: The largest anti-unification distance between the two
            sides of a clone; -1 keeps every candidate the suffix tree finds.
        clustering_threshold: The largest cost of adding a statement to a cluster.
        hashing_depth: How deep the rough hash of a statement looks.
        force: Keep long runs of statements that all have the same mark.
    """

    size_threshold: int = 5
    distance_threshold: int = 5
    clustering_threshold: int = 10
    hashing_depth: int = 1
    force: bool = False


@dataclass(frozen=True)
class Clone:
    """Two runs of statements that are copies of one another, up to small differences.

    Attributes:
        first: The statements of one copy.
        second: The statements of the other.
        distance: How much they differ, by anti-unification.
    """

    first: tuple[Statement, ...]
    second: tuple[Statement, ...]
    distance: float


def covered_lines(sequence: Iterable[Statement]) -> frozenset[int]:
    """Collect the source lines a run of statements spans.

    Args:
        sequence: The statements.

    Returns:
        Every line they cover.
    """
    return frozenset().union(*(statement.covered_lines for statement in sequence))


def dcup_hash(node: Node, level: int) -> int:
    """Hash the top of a tree only, so that trees of the same rough shape collide.

    Leaves count for nothing: two statements that differ only in their names and
    constants fall in the same bucket.

    Args:
        node: The tree.
        level: How many levels below the root take part.

    Returns:
        The hash.
    """
    if node.is_leaf:
        return 0
    total = (level + 1) * hash(node.label) * len(node.children)
    if level != 0:
        total += sum(
            position * dcup_hash(child, level - 1)
            for position, child in enumerate(node.children, start=1)
        )
    return hash(total)


def sequence_tree(sequence: Sequence[Statement]) -> Node:
    """Join a run of statements under one root, to compare two runs at once.

    Args:
        sequence: The statements.

    Returns:
        A node labelled `__SEQUENCE__` whose children are the statements' trees.
    """
    return Node("__SEQUENCE__", (statement.tree for statement in sequence))


def _buckets(sequences: Sequence[Sequence[Statement]], depth: int) -> dict[int, list[Statement]]:
    buckets: dict[int, list[Statement]] = {}
    for sequence in sequences:
        for statement in sequence:
            buckets.setdefault(dcup_hash(statement.tree, depth), []).append(statement)
    return buckets


def _build_clusters(statements: Sequence[Statement], threshold: int) -> list[Cluster]:
    clusters: list[Cluster] = []
    for statement in statements:
        costs = [(cluster.add_cost(statement.tree), cluster) for cluster in clusters]
        best = min(costs, key=itemgetter(0), default=None)
        if best is None or best[0] > threshold:
            clusters.append(Cluster(statement.tree))
        else:
            best[1].unify(statement.tree)
    return clusters


def _mark(statements: Sequence[Statement], clusters: Sequence[Cluster]) -> None:
    for statement in statements:
        lowest = sys.float_info.max
        for cluster in clusters:
            # Kept from 1.1.0: every cluster that improves on the previous best receives
            # the statement, which raises its largest number of covered lines.
            cost = anti_unify(cluster.pattern or statement.tree, statement.tree).distance
            if cost < lowest:
                lowest = cost
                statement.mark = cluster
                cluster.add_without_unification(statement.tree)


def drop_long_equal_runs(sequences: Sequence[Sequence[Statement]]) -> list[list[Statement]]:
    """Cut out of each sequence the runs of statements that all share one mark.

    A run is cut once more than `MAX_EQUAL_MARKS` statements follow its first one with
    the same mark; the pieces on each side become sequences of their own.

    Args:
        sequences: The marked statement sequences.

    Returns:
        The sequences, with those runs taken out.
    """
    kept_sequences: list[list[Statement]] = []
    for sequence in sequences:
        kept: list[Statement | None] = list(sequence)
        current: object = None
        repeats = 0
        start = 0
        for index, statement in enumerate(sequence):
            if statement.mark is not current:
                current, repeats, start = statement.mark, 0, index
                continue
            repeats += 1
            if repeats > MAX_EQUAL_MARKS:
                kept[start : index + 1] = [None] * (index + 1 - start)
        run: list[Statement] = []
        for item in [*kept, None]:
            if item is None:
                if run:
                    kept_sequences.append(run)
                run = []
            else:
                run.append(item)
    return kept_sequences


def _candidates(
    sequences: Sequence[Sequence[Statement]], threshold: int
) -> list[tuple[tuple[Statement, ...], tuple[Statement, ...]]]:
    def mark_of(statement: Statement) -> Hashable:
        return statement.mark

    def weight(code: Hashable) -> float:
        # A run is as heavy as the largest statement each of its clusters has received.
        return code.max_covered_lines if isinstance(code, Cluster) else 0

    tree: SuffixTree[Statement] = SuffixTree(mark_of)
    for sequence in sequences:
        tree.add(sequence)
    pairs = tree.best_max_substrings(threshold, weight, lambda run: len(covered_lines(run)))
    return [(tuple(first), tuple(second)) for first, second in pairs]


def refine(
    candidates: list[tuple[tuple[Statement, ...], tuple[Statement, ...]]], settings: Settings
) -> list[Clone]:
    """Shrink each candidate pair to its longest window that is close enough.

    The window is searched from the longest to the shortest, and from the left; what
    remains on each side of it is searched again.

    Args:
        candidates: Pairs of statement runs with the same marks; consumed.
        settings: The size and distance thresholds.

    Returns:
        The clones found.
    """
    clones: list[Clone] = []
    while candidates:
        first, second = candidates.pop()
        for length in range(len(first), 0, -1):
            found = _closest_window(first, second, length, settings)
            if found is None:
                continue
            start, clone = found
            clones.append(clone)
            # Kept from 1.1.0: the part before the window loses its last statement.
            if start > 0:
                candidates.append((first[: start - 1], second[: start - 1]))
            if start + length < len(first):
                candidates.append((first[start + length :], second[start + length :]))
            break
    return clones


def _closest_window(
    first: tuple[Statement, ...], second: tuple[Statement, ...], length: int, settings: Settings
) -> tuple[int, Clone] | None:
    for start in range(len(first) - length + 1):
        one, other = first[start : start + length], second[start : start + length]
        if min(len(covered_lines(one)), len(covered_lines(other))) < settings.size_threshold:
            continue
        distance = anti_unify(sequence_tree(one), sequence_tree(other)).distance
        if distance < settings.distance_threshold:
            return start, Clone(one, other, distance)
    return None


def without_dominated(clones: Sequence[Clone]) -> list[Clone]:
    """Drop the clones that lie inside the two copies of another clone.

    Args:
        clones: The clones found.

    Returns:
        Those whose first copy is not nested in one side of a clone whose other side
        holds their second copy.
    """
    by_statement: dict[int, list[Clone]] = {}
    for clone in clones:
        for statement in (*clone.first, *clone.second):
            by_statement.setdefault(id(statement), []).append(clone)

    def dominated(clone: Clone) -> bool:
        outer_second = {id(ancestor) for ancestor in clone.second[0].ancestors}
        for ancestor in clone.first[0].ancestors:
            for other in by_statement.get(id(ancestor), []):
                side = other.second if ancestor in other.first else other.first
                if any(id(statement) in outer_second for statement in side):
                    return True
        return False

    return [clone for clone in clones if not dominated(clone)]


def find_clones(files: Sequence[SourceFile], settings: Settings | None = None) -> list[Clone]:
    """Find the clones across a set of files.

    Args:
        files: The parsed files.
        settings: The thresholds; the defaults of Clone Digger 1.1.0 when left out.

    Returns:
        The clones, each a pair of statement runs with their distance.
    """
    settings = settings or Settings()
    sequences: Sequence[Sequence[Statement]] = [
        sequence
        for file in files
        for sequence in file.sequences
        if len(covered_lines(sequence)) >= settings.size_threshold
    ]
    buckets = _buckets(sequences, settings.hashing_depth)
    for statements in buckets.values():
        _mark(statements, _build_clusters(statements, settings.clustering_threshold))
    if not settings.force:
        sequences = drop_long_equal_runs(sequences)
    candidates = _candidates(sequences, settings.size_threshold)
    if settings.distance_threshold == -1:
        return [
            Clone(first, second, anti_unify(sequence_tree(first), sequence_tree(second)).distance)
            for first, second in candidates
        ]
    return without_dominated(refine(candidates, settings))
