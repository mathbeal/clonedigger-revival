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

from dataclasses import dataclass
from itertools import groupby
from operator import itemgetter
from typing import TYPE_CHECKING, cast

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

# The root that joins a run of statements, as Clone Digger 1.1.0 named it.
SEQUENCE_LABEL = "__SEQUENCE__"


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
        A node labelled `SEQUENCE_LABEL` whose children are the statements' trees.
    """
    return Node(SEQUENCE_LABEL, (statement.tree for statement in sequence))


def buckets_by_shape(
    sequences: Sequence[Sequence[Statement]], depth: int
) -> dict[int, list[Statement]]:
    """Put the statements of the same rough shape together.

    Args:
        sequences: The statement sequences.
        depth: How deep `dcup_hash` looks.

    Returns:
        The statements, by their rough hash, in the order they come.
    """
    buckets: dict[int, list[Statement]] = {}
    for sequence in sequences:
        for statement in sequence:
            buckets.setdefault(dcup_hash(statement.tree, depth), []).append(statement)
    return buckets


def build_clusters(statements: Sequence[Statement], threshold: int) -> list[Cluster]:
    """Build clusters of statements around common patterns.

    Each statement joins the cluster it costs least to widen, if that cost is at most
    `threshold`; otherwise it starts a cluster of its own.

    Args:
        statements: The statements of one bucket, in order.
        threshold: The largest cost of joining a cluster.

    Returns:
        The clusters, in the order they were started.
    """
    clusters: list[Cluster] = []
    for statement in statements:
        costs = [(cluster.add_cost(statement.tree), cluster) for cluster in clusters]
        best = min(costs, key=itemgetter(0), default=None)
        if best is None or best[0] > threshold:
            clusters.append(Cluster(statement.tree))
        else:
            best[1].unify(statement.tree)
    return clusters


def mark_statements(statements: Sequence[Statement], clusters: Sequence[Cluster]) -> None:
    """Label each statement with the cluster whose pattern it is closest to.

    Args:
        statements: The statements of one bucket.
        clusters: The clusters built from that bucket.
    """
    for statement in statements:
        # The cluster whose pattern the statement is closest to, the first on a tie.
        # Clone Digger 1.1.0 also added the statement to every cluster that improved on
        # the best so far, which inflated their sizes; only the chosen one receives it.
        distances = [_distance_to(cluster, statement.tree) for cluster in clusters]
        best = clusters[distances.index(min(distances))]
        statement.mark = best
        best.add_without_unification(statement.tree)


def _distance_to(cluster: Cluster, tree: Node) -> float:
    return anti_unify(cluster.pattern or tree, tree).distance


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
        piece: list[Statement] = []
        for _, group in groupby(sequence, key=lambda statement: id(statement.mark)):
            run = list(group)
            if len(run) <= MAX_EQUAL_MARKS + 1:
                piece.extend(run)
                continue
            if piece:
                kept_sequences.append(piece)
            piece = []
        if piece:
            kept_sequences.append(piece)
    return kept_sequences


def _candidates(
    sequences: Sequence[Sequence[Statement]], threshold: int
) -> list[tuple[tuple[Statement, ...], tuple[Statement, ...]]]:
    def mark_of(statement: Statement) -> Hashable:
        return statement.mark

    def weight(code: Hashable) -> float:
        # A run is as heavy as the largest statement each of its clusters has received;
        # every mark is a cluster.
        return cast("Cluster", code).max_covered_lines  # pragma: no mutate - cast does nothing

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
            # What lies on each side of the window is searched again. Clone Digger 1.1.0
            # searched first[:start - 1] before it, which left out the statement just
            # before the window.
            end = start + length
            before = (first[:start], second[:start])
            after = (first[end:], second[end:])
            # Both sides of a part have the same length: testing one is enough.
            candidates.extend(part for part in (before, after) if part[0])  # pragma: no mutate
            break
    return clones


def _closest_window(
    first: tuple[Statement, ...], second: tuple[Statement, ...], length: int, settings: Settings
) -> tuple[int, Clone] | None:
    # The starts of every window of `length` statements. A mutated bound would add
    # shorter windows at the end, which a later, shorter length tries anyway.
    starts = range(len(first) - length + 1)  # pragma: no mutate
    for start in starts:
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
    buckets = buckets_by_shape(sequences, settings.hashing_depth)
    for statements in buckets.values():
        mark_statements(statements, build_clusters(statements, settings.clustering_threshold))
    if not settings.force:
        sequences = drop_long_equal_runs(sequences)
    candidates = _candidates(sequences, settings.size_threshold)
    if settings.distance_threshold == -1:
        return [
            Clone(first, second, anti_unify(sequence_tree(first), sequence_tree(second)).distance)
            for first, second in candidates
        ]
    return without_dominated(refine(candidates, settings))
