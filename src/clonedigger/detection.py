# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, clone_detection_algorithm.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: ported to Python 3, split in steps;
# 2026-10-08: windows searched in square time, labels hashed the same in every run,
# every function documented; 2026-10-23: a statement that is the pattern of a cluster
# marked without weighing any)
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

import hashlib
import math
from dataclasses import dataclass
from functools import cache
from itertools import groupby
from typing import TYPE_CHECKING, cast

from clonedigger.anti_unification import Cluster, anti_unify, difference
from clonedigger.suffix_tree import SuffixTree
from clonedigger.tree import Node

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Iterator, Sequence

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


@cache
def label_hash(label: str) -> int:
    """Hash a label the same way in every run.

    `hash` of a string changes with every run of Python, unless PYTHONHASHSEED is
    set: two runs would then disagree on which shapes collide, and could put
    statements in other buckets. Python 2, which Clone Digger 1.1.0 ran on, did not
    vary it.

    Args:
        label: The label of a node.

    Returns:
        The first 8 bytes of its BLAKE2b digest, as an integer.
    """
    return int.from_bytes(hashlib.blake2b(label.encode(), digest_size=8).digest())


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
    total = (level + 1) * label_hash(node.label) * len(node.children)
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
    # Any cost above the threshold means a new cluster: weighing can stop there.
    above = math.nextafter(threshold, math.inf)
    for statement in statements:
        best: Cluster | None = None  # pragma: no mutate - any value loses to an inf cost
        lowest = math.inf
        for cluster in clusters:
            # The first cluster of lowest cost wins; one that cannot beat it, or that
            # costs more than the threshold, stops being weighed early.
            # The limit only saves time: the decision is the same without it.
            cost = cluster.add_cost(statement.tree, min(lowest, above))  # pragma: no mutate
            if cost < lowest:
                best, lowest = cluster, cost
        if best is None or lowest > threshold:
            clusters.append(Cluster(statement.tree))
        else:
            best.unify(statement.tree)
    return clusters


def mark_statements(statements: Sequence[Statement], clusters: Sequence[Cluster]) -> None:
    """Label each statement with the cluster whose pattern it is closest to.

    A statement that is itself the pattern of a cluster is at a distance of zero from
    it, and no distance is smaller: `_by_pattern` reads off which cluster receives it,
    and not one is weighed. The others go to `_closest`, which weighs them against
    every cluster of the bucket, and is where the time of a large run goes.

    Args:
        statements: The statements of one bucket.
        clusters: The clusters built from that bucket.
    """
    patterns = _by_pattern(clusters)
    # The cluster each statement was gathered into: likely the closest, so weighing it
    # first gives a tight limit for all the others.
    # Like the limits below, it only saves time: the closest cluster is the same without.
    home = _homes(clusters)
    for statement in statements:
        best = patterns.get(statement.tree)  # pragma: no mutate - time only
        if best is None:
            best = _closest(clusters, statement.tree, home)
        statement.mark = best
        best.add_without_unification(statement.tree)


def _by_pattern(clusters: Sequence[Cluster]) -> dict[Node, Cluster]:
    """Find, for each pattern, the first cluster that holds it.

    A cluster made without a tree has no pattern, and `_closest` reads it as being at a
    distance of zero from every statement: the clusters after it are left out, so that
    it keeps the statements it would receive.

    Filling the table saves time only, `_closest` choosing the same cluster: a change
    that leaves it empty gives the same marks, so the two lines that fill it are left
    out of mutation testing. One that fills it with another cluster marks a statement
    with another cluster, and the tests catch that, as they catch a missing `break`.

    Args:
        clusters: The clusters of a bucket, in the order they were started.

    Returns:
        The first cluster holding each pattern, up to the first cluster without one.
    """
    patterns: dict[Node, Cluster] = {}
    for cluster in clusters:
        if cluster.pattern is None:  # pragma: no mutate - time only
            break
        patterns.setdefault(cluster.pattern, cluster)  # pragma: no mutate - time only
    return patterns


def _closest(clusters: Sequence[Cluster], tree: Node, home: dict[int, Cluster]) -> Cluster:
    """Weigh a statement against every cluster and keep the closest, the first on a tie.

    Clone Digger 1.1.0 also added the statement to every cluster that improved on the
    best so far, which inflated their sizes; only the chosen one receives it.

    Args:
        clusters: The clusters of a bucket, in the order they were started.
        tree: The statement's tree.
        home: The cluster each gathered tree belongs to, by the identity of the tree.

    Returns:
        The cluster whose pattern the statement is closest to.
    """
    # A cluster stops being weighed once it cannot be closer than the best so far.
    start = home.get(id(tree))  # pragma: no mutate - time only
    known = _known_distance(start, tree)  # pragma: no mutate - time only
    # Just above the known distance: a cluster as close but earlier still wins.
    ceiling = math.nextafter(known, math.inf)
    best, lowest = clusters[0], math.inf
    for cluster in clusters:
        distance = _distance_to(cluster, tree, min(lowest, ceiling))
        if distance < lowest:
            best, lowest = cluster, distance
    return best


def _homes(clusters: Sequence[Cluster]) -> dict[int, Cluster]:
    """Find the cluster each statement was gathered into.

    Args:
        clusters: The clusters of a bucket.

    Returns:
        Each cluster, keyed by the identity of the trees it holds.
    """
    return {id(t): c for c in clusters for t in c.trees}  # pragma: no mutate - time only


def _known_distance(home: Cluster | None, tree: Node) -> float:
    """Weigh a statement against the cluster it was gathered into.

    Args:
        home: That cluster, or None if the statement was not gathered.
        tree: The statement's tree.

    Returns:
        Their distance; infinity without a cluster.
    """
    return math.inf if home is None else _distance_to(home, tree, math.inf)  # pragma: no mutate


def _distance_to(cluster: Cluster, tree: Node, limit: float) -> float:
    """Weigh how far a statement is from the pattern of a cluster.

    Args:
        cluster: The cluster.
        tree: The statement's tree.
        limit: The weighing stops once it reaches this much.

    Returns:
        The distance, or a value of at least `limit`.
    """
    # The limit only saves time: the closest cluster is the same without it.
    return sum(difference(cluster.pattern or tree, tree, limit))  # pragma: no mutate


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
) -> Iterator[tuple[tuple[Statement, ...], tuple[Statement, ...]]]:
    """Find the runs of marks that occur twice, with a suffix tree.

    Args:
        sequences: The marked statement sequences.
        threshold: The fewest lines a run must weigh and span.

    Returns:
        The candidate pairs of runs, one at a time.
    """

    def mark_of(statement: Statement) -> Hashable:
        """Read the mark of a statement: the cluster it was given.

        Args:
            statement: The statement.

        Returns:
            Its mark.
        """
        return statement.mark

    def weight(code: Hashable) -> float:
        """Weigh one mark.

        Args:
            code: The mark, a cluster.

        Returns:
            The most lines a statement of that cluster spans.
        """
        # A run is as heavy as the largest statement each of its clusters has received;
        # every mark is a cluster.
        return cast("Cluster", code).max_covered_lines  # pragma: no mutate - cast does nothing

    tree: SuffixTree[Statement] = SuffixTree(mark_of)
    for sequence in sequences:
        tree.add(sequence)
    pairs = tree.iter_best_max_substrings(threshold, weight, lambda run: len(covered_lines(run)))
    return ((tuple(first), tuple(second)) for first, second in pairs)


def refine(
    candidates: Iterable[tuple[tuple[Statement, ...], tuple[Statement, ...]]], settings: Settings
) -> list[Clone]:
    """Shrink each candidate pair to its longest window that is close enough.

    The window is searched from the longest to the shortest, and from the left; what
    remains on each side of it is searched again.

    Args:
        candidates: Pairs of statement runs with the same marks, read one at a time:
            each is refined on its own, so millions of them need not be held at once.
        settings: The size and distance thresholds.

    Returns:
        The clones found.
    """
    clones: list[Clone] = []
    for candidate in candidates:
        clones.extend(_refine_one(candidate, settings))
    return clones


def _refine_one(
    candidate: tuple[tuple[Statement, ...], tuple[Statement, ...]], settings: Settings
) -> list[Clone]:
    """Shrink one candidate to its clones: the longest window, then what lies around it.

    Args:
        candidate: Two runs of statements with the same marks.
        settings: The size and distance thresholds.

    Returns:
        The clones found in it.
    """
    clones: list[Clone] = []
    parts = [candidate]
    while parts:
        first, second = parts.pop()
        found = _longest_window(first, second, settings)
        if found is None:
            continue
        start, end, clone = found
        clones.append(clone)
        # What lies on each side of the window is searched again. Clone Digger 1.1.0
        # searched first[:start - 1] before it, which left out the statement just
        # before the window.
        before = (first[:start], second[:start])
        after = (first[end:], second[end:])
        # Both sides of a part have the same length: testing one is enough.
        parts.extend(part for part in (before, after) if part[0])  # pragma: no mutate
    return clones


def _longest_window(
    first: tuple[Statement, ...], second: tuple[Statement, ...], settings: Settings
) -> tuple[int, int, Clone] | None:
    """Find the longest window close enough and large enough, the leftmost on a tie.

    Clone Digger 1.1.0 tried every length from the longest down, and every start from
    the left: a cube of the length of the candidate, which a run of a few hundred
    similar statements made endless. Two facts give the same window far sooner:

    - widening a window only adds pairs of differing subtrees, each of positive
      weight, so its distance never shrinks: if the window one statement longer than
      the best so far is not close enough, no longer window from that start is;
    - widening a window only adds lines: if the widest close window from a start is
      too small, every window from that start is.

    Each start is thus weighed once, against the best so far, and only a start that
    beats it is widened, one statement at a time: most windows are short, and
    longer leaps cost more than they save (measured on the standard library and on
    runs of 800 statements).

    Args:
        first: One side of the candidate.
        second: The other, as long.
        settings: The size and distance thresholds.

    Returns:
        The start and the end of the window, and the clone it makes; None when no
        window is both close enough and large enough.
    """
    best: tuple[int, int] | None = None
    longest = 0
    # Most often the whole candidate is the clone: one weighing then settles it.
    if _large(first, second, settings) and _close(first, second, settings):
        best, longest = (0, len(first)), len(first)
    for start in range(len(first)):
        end = start + longest + 1
        # Past this start, even the rest of the candidate is too short or too small.
        if end > len(first) or not _large(first[start:], second[start:], settings):
            break
        # The rest is large enough, so some end is: the first one is the cheapest to weigh.
        while not _large(first[start:end], second[start:end], settings):
            end += 1
        if not _close(first[start:end], second[start:end], settings):
            continue
        # One past the end slices to the same window, and leaves nothing after it.
        while end < len(first):  # pragma: no mutate
            if not _close(first[start : end + 1], second[start : end + 1], settings):
                break
            end += 1
        best, longest = (start, end), end - start
    if best is None:
        return None
    start, end = best
    one, other = first[start:end], second[start:end]
    distance = _sequence_distance(one, other, settings.distance_threshold)
    return start, end, Clone(one, other, distance)


def _large(one: Sequence[Statement], other: Sequence[Statement], settings: Settings) -> bool:
    """Tell whether both sides of a window span enough lines.

    Args:
        one: One side.
        other: The other.
        settings: The size threshold.

    Returns:
        Whether each side spans at least `size_threshold` lines.
    """
    return min(len(covered_lines(one)), len(covered_lines(other))) >= settings.size_threshold


def _close(one: Sequence[Statement], other: Sequence[Statement], settings: Settings) -> bool:
    """Tell whether the two sides of a window are close enough to be a clone.

    Args:
        one: One side.
        other: The other, as long.
        settings: The distance threshold.

    Returns:
        Whether their distance is under `distance_threshold`.
    """
    # Only whether the distance is under the threshold matters: the weighing stops there.
    limit = settings.distance_threshold
    return _sequence_distance(one, other, limit) < limit


def _sequence_distance(one: Sequence[Statement], other: Sequence[Statement], limit: float) -> float:
    """Weigh how far two runs of statements are, joined each under one root.

    Args:
        one: One run.
        other: The other, as long.
        limit: The weighing stops once it reaches this much.

    Returns:
        Their anti-unification distance, or a value of at least `limit`.
    """
    pair = (sequence_tree(one), sequence_tree(other))
    return sum(difference(*pair, limit))  # pragma: no mutate - the limit only saves time


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
        """Tell whether another clone holds both copies of this one.

        Args:
            clone: The clone.

        Returns:
            Whether a statement around its first copy is one side of a clone whose
            other side holds a statement around its second copy.
        """
        outer_second = {id(ancestor) for ancestor in clone.second[0].ancestors}
        for ancestor in clone.first[0].ancestors:
            for other in by_statement.get(id(ancestor), []):
                side = other.second if ancestor in other.first else other.first
                if any(id(statement) in outer_second for statement in side):
                    return True
        return False

    return [clone for clone in clones if not dominated(clone)]


def long_sequences(files: Sequence[SourceFile], settings: Settings) -> list[Sequence[Statement]]:
    """Keep the statement sequences that span enough lines: the first step of the run.

    Args:
        files: The parsed files.
        settings: The size threshold.

    Returns:
        The sequences spanning at least `size_threshold` lines, in the order they come.
    """
    return [
        sequence
        for file in files
        for sequence in file.sequences
        if len(covered_lines(sequence)) >= settings.size_threshold
    ]


def find_clones(files: Sequence[SourceFile], settings: Settings | None = None) -> list[Clone]:
    """Find the clones across a set of files.

    Args:
        files: The parsed files.
        settings: The thresholds; the defaults of Clone Digger 1.1.0 when left out.

    Returns:
        The clones, each a pair of statement runs with their distance.
    """
    settings = settings or Settings()
    sequences: Sequence[Sequence[Statement]] = long_sequences(files, settings)
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
