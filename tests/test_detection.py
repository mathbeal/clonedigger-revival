# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pipeline finds the clones Clone Digger 1.1.0 found, and only those."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import] - see the hash test
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from hypothesis import given
from hypothesis import strategies as st

from clonedigger.anti_unification import Cluster, difference
from clonedigger.detection import (
    MAX_EQUAL_MARKS,
    SEQUENCE_LABEL,
    Clone,
    Settings,
    buckets_by_shape,
    build_clusters,
    covered_lines,
    dcup_hash,
    drop_long_equal_runs,
    find_clones,
    label_hash,
    mark_statements,
    refine,
    sequence_tree,
    without_dominated,
)
from clonedigger.python_frontend import Statement, read_source
from clonedigger.report import Span
from clonedigger.tree import Node

GOLDEN = Path(__file__).parent / "golden"


def golden_files() -> list:  # type: ignore[type-arg]
    """Read the two input files the original release was run on.

    Returns:
        The parsed files.
    """
    return [
        read_source(Path("inputs") / path.name, path.read_text())
        for path in sorted((GOLDEN / "inputs").glob("*.py"))
    ]


def test_finds_the_clone_the_original_found() -> None:
    """On the recorded inputs, the one clone of 1.1.0, at the same lines."""
    expected = re.findall(
        r'<file line="(\d+)" path="([^"]+)"/>', (GOLDEN / "cpd_default.xml").read_text()
    )
    (clone,) = find_clones(golden_files())
    starts = {
        (str(Span.of(side).path), Span.of(side).start) for side in (clone.first, clone.second)
    }
    assert starts == {(path, int(line)) for line, path in expected}
    assert Span.of(clone.first).end - Span.of(clone.first).start == 5


def test_no_distance_threshold_keeps_every_candidate() -> None:
    """With distance -1 the candidates are returned unrefined, with their distance."""
    clones = find_clones(golden_files(), Settings(distance_threshold=-1))
    assert clones
    assert all(clone.distance >= 0 for clone in clones)


def test_a_tight_distance_finds_nothing() -> None:
    """Copies that differ by renaming are not clones at a distance threshold of 1."""
    assert find_clones(golden_files(), Settings(distance_threshold=1)) == []


def test_short_sequences_are_ignored() -> None:
    """A copy shorter than the size threshold is not reported."""
    assert find_clones(golden_files(), Settings(size_threshold=30)) == []


def test_dominated_clones_are_dropped() -> None:
    """A clone inside two copied functions is not reported twice."""
    body = """
        def {name}(items):
            total = 0
            for item in items:
                price = item.price * item.quantity
                if item.discount:
                    price = price - item.discount
                    price = max(price, 0)
                    price = round(price, 2)
                    price = price + 0
                    price = price * 1
                    price = price - 0
                total = total + price
            return total
        """
    files = [read_source(Path(f"{name}.py"), dedent(body.format(name=name))) for name in ("a", "b")]
    clones = find_clones(files, Settings(size_threshold=3))
    nested = [c for c in clones if c.first[0].tree.label == "Assign" and c.first[0].ancestors]
    outer = [c for c in clones if not c.first[0].ancestors]
    assert outer
    assert all(inner.first[0].ancestors[0] not in outer[0].first for inner in nested)


def test_long_runs_of_equal_marks_are_left_out() -> None:
    """More than MAX_EQUAL_MARKS statements in a row with one mark break the sequence."""
    cluster, other = Cluster(Node("x")), Cluster(Node("y"))
    path = Path("long.py")
    run = [Statement(Node("x"), path, mark=cluster) for _ in range(MAX_EQUAL_MARKS + 2)]
    before = Statement(Node("y"), path, mark=other)
    after = Statement(Node("y"), path, mark=other)
    assert drop_long_equal_runs([[before, *run, after]]) == [[before], [after]]
    short = run[: MAX_EQUAL_MARKS + 1]
    assert drop_long_equal_runs([[before, *short]]) == [[before, *short]]


def test_force_keeps_long_runs() -> None:
    """With force, a file of many similar assignments still yields its clones."""
    lines = "".join(f"value_{index} = compute({index})\n" for index in range(15))
    files = [read_source(Path(f"{name}.py"), lines) for name in ("a", "b")]
    assert find_clones(files) == []
    assert find_clones(files, Settings(force=True))


def test_rough_hash_ignores_leaves() -> None:
    """Statements that differ only in names and constants share a bucket."""
    one = Node("Assign", (Node("AssName", (Node("'a'"),)), Node("Constant", (Node("1"),))))
    other = Node("Assign", (Node("AssName", (Node("'b'"),)), Node("Constant", (Node("2"),))))
    assert dcup_hash(one, 1) == dcup_hash(other, 1)
    assert dcup_hash(Node("leaf"), 3) == 0


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_rough_hash_tells_shapes_apart(depth: int) -> None:
    """Different labels at the top give different buckets."""
    assign = Node("Assign", (Node("Name", (Node("x"),)),))
    call = Node("Call", (Node("Name", (Node("x"),)),))
    assert dcup_hash(assign, depth) != dcup_hash(call, depth)


def assignment(name: str, line: int, path: str) -> Statement:
    """Build a one-line assignment statement.

    Args:
        name: The name assigned to.
        line: The line it stands on.
        path: Its file.

    Returns:
        The statement.
    """
    tree = Node("Assign", (Node("AssName", (Node(name),)), Node("1")), lines={line})
    return Statement(tree, Path(path))


def test_refining_keeps_the_part_around_the_window() -> None:
    """A clone found after the first statements leaves the rest to search, minus one."""
    first = tuple(assignment("a", line, "a.py") for line in range(1, 8))
    head = Node("Call", tuple(Node(str(index)) for index in range(12)), lines={1})
    second = (Statement(head, Path("b.py")), *(assignment("a", n, "b.py") for n in range(2, 8)))
    clones = refine([(first, second)], Settings(size_threshold=5))
    assert [len(clone.first) for clone in clones] == [6]
    assert clones[0].first == first[1:]


def test_a_clone_is_kept_when_its_neighbours_do_not_contain_it() -> None:
    """Sharing an ancestor with another clone is not enough to be dominated."""
    outer_a = assignment("x", 1, "a.py")
    outer_b = assignment("x", 1, "b.py")
    elsewhere = assignment("x", 1, "c.py")
    inner_a = Statement(Node("y", lines={2}), Path("a.py"), ancestors=(outer_a,))
    inner_b = Statement(Node("y", lines={2}), Path("b.py"), ancestors=(outer_b,))
    around = Clone((outer_a,), (elsewhere,), 0)
    inner = Clone((inner_a,), (inner_b,), 0)
    assert without_dominated([around, inner]) == [around, inner]
    containing = Clone((outer_a,), (outer_b,), 0)
    assert without_dominated([containing, inner]) == [containing]


@pytest.mark.parametrize("name", ["bottle", "six", "docopt"])
def test_finds_the_clones_of_the_original_on_real_files(name: str) -> None:
    """On real files both versions read, the same clones start at the same lines."""
    path = GOLDEN / "corpus" / f"{name}.py"
    report = (GOLDEN / "corpus" / f"{name}.cpd.xml").read_text()
    expected = {
        frozenset(map(int, pair))
        for pair in re.findall(r'<file line="(\d+)"[^>]*/>\s*<file line="(\d+)"', report)
    }
    clones = find_clones([read_source(path, path.read_text())])
    found = {frozenset({Span.of(c.first).start, Span.of(c.second).start}) for c in clones}
    assert found == expected


def renamed(count: int, line: int, side: str) -> Statement:
    """Build a call whose arguments all differ on the other side.

    Args:
        count: How many arguments.
        line: The line it stands on.
        side: "a" or "b": the file, and the prefix of every argument.

    Returns:
        A statement whose anti-unification against its twin costs `count`: each
        argument is a distinct leaf on each side.
    """
    arguments = tuple(Node(f"{side}{line}_{index}") for index in range(count))
    return Statement(Node("Call", arguments, lines={line}), Path(f"{side}.py"))


def test_refining_searches_the_whole_part_before_the_window() -> None:
    """A clone right before the chosen window is found; 1.1.0 lost its last statement."""
    first = (renamed(1, 1, "a"), renamed(4, 2, "a"), renamed(0, 3, "a"))
    second = (renamed(1, 1, "b"), renamed(4, 2, "b"), renamed(0, 3, "b"))
    # Distances 1, 4 and 0: no window of three passes, the second window of two does,
    # and what is left before it, the first statement alone, is a clone too.
    clones = refine([(first, second)], Settings(size_threshold=1))
    assert sorted(len(clone.first) for clone in clones) == [1, 2]
    assert any(clone.first == first[:1] for clone in clones)


def test_marking_gives_a_statement_to_its_closest_cluster_only() -> None:
    """The farther cluster tried first does not receive the statement, as it did in 1.1.0."""
    statement = Statement(Node("Add", (Node("a"), Node("b")), lines={1, 2, 3}), Path("x.py"))
    far = Cluster(Node("Add", (Node("x"), Node("y"))))
    near = Cluster(Node("Add", (Node("a"), Node("z"))))
    mark_statements([statement], [far, near])
    assert statement.mark is near
    assert len(far) == 1
    assert len(near) == 2


def test_rough_hash_follows_the_formula_of_the_original() -> None:
    """Root label times depth times arity, plus children weighted by their position."""
    name, const = Node("Name", (Node("'x'"),)), Node("Constant", (Node("1"),))
    tree = Node("Assign", (name, const))
    level_0 = [hash(1 * label_hash("Name") * 1), hash(1 * label_hash("Constant") * 1)]
    expected = hash(2 * label_hash("Assign") * 2 + 1 * level_0[0] + 2 * level_0[1])
    assert dcup_hash(tree, 1) == expected
    assert dcup_hash(tree, 0) == hash(1 * label_hash("Assign") * 2)


def test_a_label_hashes_the_same_in_every_run() -> None:
    """The hash of a label is its BLAKE2b digest, whatever the seed of `hash`."""
    label_hash.cache_clear()
    assert label_hash("Assign") == int.from_bytes(
        hashlib.blake2b(b"Assign", digest_size=8).digest()
    )
    # This very Python, on a script written here: nothing untrusted is run.
    script = "from clonedigger.detection import label_hash; print(label_hash('Assign'))"
    runs = {
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2")
    }
    assert runs == {f"{label_hash('Assign')}\n"}


def test_a_run_of_statements_is_joined_under_the_original_label() -> None:
    """The root of a run keeps the name Clone Digger 1.1.0 gave it."""
    assert SEQUENCE_LABEL == "__SEQUENCE__"
    statement = assignment("a", 1, "a.py")
    joined = sequence_tree([statement])
    assert joined.label == SEQUENCE_LABEL
    assert joined.children == (statement.tree,)


def test_buckets_group_statements_by_shape_in_order() -> None:
    """Same shape, same bucket, in the order the statements come."""
    first, second = assignment("a", 1, "a.py"), assignment("b", 2, "a.py")
    call = Statement(Node("Call", (Node("f"),), lines={3}), Path("a.py"))
    buckets = buckets_by_shape([[first, call, second]], 1)
    assert sorted(map(len, buckets.values())) == [1, 2]
    assert [first, second] in buckets.values()


def test_a_statement_joins_a_cluster_at_exactly_the_threshold() -> None:
    """Joining costs at most the threshold; one more and a new cluster starts."""

    def wide(prefix: str, count: int) -> Statement:
        """Build a call with distinct arguments.

        Args:
            prefix: What every argument's name starts with.
            count: How many arguments.

        Returns:
            The statement.
        """
        leaves = tuple(Node(f"{prefix}{index}") for index in range(count))
        return Statement(Node("Call", leaves), Path("a.py"))

    # Ten distinct leaves against ten others cost 10 * 0.5 + 10 * 0.5.
    assert len(build_clusters([wide("a", 10), wide("b", 10)], 10)) == 1
    assert len(build_clusters([wide("a", 10), wide("b", 10)], 9)) == 2


def test_refining_searches_the_part_after_the_window() -> None:
    """A clone after the chosen window is found too."""
    first = (renamed(0, 1, "a"), renamed(9, 2, "a"), renamed(0, 3, "a"))
    second = (renamed(0, 1, "b"), renamed(9, 2, "b"), renamed(0, 3, "b"))
    clones = refine([(first, second)], Settings(size_threshold=1))
    found = [clone.first for clone in clones]
    assert len(found) == 2
    assert first[:1] in found
    assert first[2:] in found


def test_refining_skips_small_windows_and_goes_on() -> None:
    """A window too short in lines is passed over, and the next one is tried."""

    def spread(lines: set[int], side: str) -> Statement:
        """Build a statement that spans the given lines.

        Args:
            lines: Its lines.
            side: "a" or "b", its file.

        Returns:
            The statement.
        """
        return Statement(Node("Pass", lines=lines), Path(f"{side}.py"))

    first = (spread({1}, "a"), spread({2, 3, 4}, "a"), spread({5, 6, 7}, "a"))
    second = (spread({1}, "b"), spread({2, 3, 4}, "b"), spread({5, 6, 7}, "b"))
    clones = refine([(first, second)], Settings(size_threshold=5))
    assert [clone.first for clone in clones] == [first]
    shorter = refine([(first[1:], second[1:])], Settings(size_threshold=5))
    assert [clone.first for clone in shorter] == [first[1:]]
    tail = (spread({1}, "a"), spread({2}, "a"), spread({3, 4, 5, 6, 7}, "a"))
    other = (spread({1}, "b"), spread({9}, "b"), spread({3, 4, 5, 6, 7}, "b"))
    assert [c.first for c in refine([(tail, other)], Settings(size_threshold=5))] == [tail]


def test_dominance_looks_at_the_other_side_of_the_enclosing_clone() -> None:
    """An ancestor found on the second side of a clone points to its first side."""
    outer_a = assignment("x", 1, "a.py")
    outer_b = assignment("x", 1, "b.py")
    inner_a = Statement(Node("y", lines={2}), Path("a.py"), ancestors=(outer_a,))
    inner_b = Statement(Node("y", lines={2}), Path("b.py"), ancestors=(outer_b,))
    enclosing = Clone((outer_b,), (outer_a,), 0)
    inner = Clone((inner_a,), (inner_b,), 0)
    assert without_dominated([enclosing, inner]) == [enclosing]


def test_sequences_of_exactly_the_size_threshold_are_kept() -> None:
    """A copy spanning exactly the threshold in lines is a clone."""
    clones = find_clones(golden_files(), Settings(size_threshold=6))
    assert len(clones) == 1
    assert len(covered_lines(clones[0].first)) == 6


def test_unrefined_candidates_keep_both_copies() -> None:
    """With distance -1, each candidate has its two copies, from the two places."""
    for clone in find_clones(golden_files(), Settings(distance_threshold=-1)):
        assert clone.first
        assert clone.second
        assert clone.first[0] is not clone.second[0]


def test_a_small_first_window_does_not_stop_the_search() -> None:
    """A window too short in lines is skipped, and the next one of that length is tried."""

    def statement(leaves: int, lines: set[int], side: str) -> Statement:
        """Build a call whose arguments all differ on the other side.

        Args:
            leaves: How many arguments for each line.
            lines: The lines it spans.
            side: "a" or "b": its file, and the prefix of every argument.

        Returns:
            The statement.
        """
        names = tuple(Node(f"{side}{line}_{index}") for index in range(leaves) for line in lines)
        return Statement(Node("Call", names, lines=lines), Path(f"{side}.py"))

    first = (statement(9, {1}, "a"), statement(0, {2, 3, 4}, "a"), statement(0, {5, 6, 7}, "a"))
    second = (statement(9, {1}, "b"), statement(0, {2, 3, 4}, "b"), statement(0, {5, 6, 7}, "b"))
    # All three differ by 9; the first two span 4 lines, too few; the last two are kept.
    clones = refine([(first, second)], Settings(size_threshold=5))
    assert [clone.first for clone in clones] == [first[1:]]


def test_sequences_spanning_exactly_the_threshold_take_part() -> None:
    """A body of exactly size_threshold lines can be a clone."""
    module = "b = {a}\nc = b\nd = c\ne = d\nf = e\n"
    files = [read_source(Path(f"{n}.py"), module.format(a=n)) for n in ("x", "y")]
    assert len(find_clones(files, Settings(size_threshold=5))) == 1
    assert find_clones(files, Settings(size_threshold=6)) == []


def test_ties_go_to_the_first_cluster() -> None:
    """Two clusters at the same distance: the first one gets the statement."""
    statement = Statement(Node("Add", (Node("a"), Node("b"))), Path("x.py"))
    first = Cluster(Node("Add", (Node("a"), Node("c"))))
    second = Cluster(Node("Add", (Node("a"), Node("d"))))
    mark_statements([statement], [first, second])
    assert statement.mark is first


def test_joining_ties_go_to_the_first_cluster() -> None:
    """A statement that costs the same to two clusters joins the first one."""

    def call(*names: str) -> Statement:
        """Build a call of the given names.

        Args:
            *names: Its arguments.

        Returns:
            The statement.
        """
        return Statement(Node("Call", tuple(Node(name) for name in names)), Path("x.py"))

    first, second = call("p1", "p2", "q"), call("r1", "r2", "q")
    # The two differ twice: over the threshold of 1, two clusters. The third differs
    # once from each: a tie at 1, which goes to the first cluster.
    clusters = build_clusters([first, second, call("p1", "r2", "q")], 1)
    assert [len(cluster) for cluster in clusters] == [2, 1]


def exhaustive_refine(first: tuple[Statement, ...], second: tuple[Statement, ...]) -> list[Clone]:
    """Refine a candidate as Clone Digger 1.1.0 did: every length, every start.

    Args:
        first: One side of the candidate.
        second: The other, as long.

    Returns:
        The clones, in the order the stack of parts gives them.
    """
    settings = Settings()
    clones: list[Clone] = []
    parts = [(first, second)]
    while parts:
        one, other = parts.pop()
        for length in range(len(one), 0, -1):
            window = next(
                (
                    (start, distance)
                    for start in range(len(one) - length + 1)
                    if min(
                        len(covered_lines(one[start : start + length])),
                        len(covered_lines(other[start : start + length])),
                    )
                    >= settings.size_threshold
                    and (
                        distance := sum(
                            difference(
                                sequence_tree(one[start : start + length]),
                                sequence_tree(other[start : start + length]),
                            )
                        )
                    )
                    < settings.distance_threshold
                ),
                None,
            )
            if window is not None:
                start, distance = window
                end = start + length
                clones.append(Clone(one[start:end], other[start:end], distance))
                parts.extend(
                    part
                    for part in ((one[:start], other[:start]), (one[end:], other[end:]))
                    if part[0]
                )
                break
    return clones


# A statement: how many lines it spans, and the names it uses on each side.
STATEMENTS = st.lists(
    st.tuples(
        st.integers(1, 3),
        st.lists(st.sampled_from("abc"), min_size=1, max_size=3),
        st.lists(st.sampled_from("abe"), min_size=1, max_size=3),
    ),
    min_size=1,
    max_size=14,
)


@given(STATEMENTS)
def test_refining_finds_the_windows_an_exhaustive_search_finds(
    statements: list[tuple[int, list[str], list[str]]],
) -> None:
    """The windows found are those of trying every length and every start, as 1.1.0 did.

    Names repeat within and across statements, so that pairs of differing names are
    shared, as anti-unification shares them; statements of several lines make some
    windows too small.
    """
    sides: tuple[list[Statement], list[Statement]] = ([], [])
    line = 1
    for span, *names in statements:
        lines = set(range(line, line + span))
        for side, (path, used) in zip(sides, zip("ab", names, strict=True), strict=True):
            tree = Node("Call", tuple(Node(name) for name in used), lines=lines)
            side.append(Statement(tree, Path(f"{path}.py")))
        line += span
    first, second = tuple(sides[0]), tuple(sides[1])
    assert refine([(first, second)], Settings()) == exhaustive_refine(first, second)


def marks_by_weighing_every_cluster(
    statements: list[Statement], clusters: list[Cluster]
) -> list[Cluster]:
    """Mark statements the plain way: weigh every cluster, keep the closest.

    Args:
        statements: The statements of one bucket.
        clusters: The clusters built from that bucket.

    Returns:
        The cluster each statement belongs to, in the order of the statements.
    """
    marks = []
    for statement in statements:
        distances = [
            sum(difference(cluster.pattern or statement.tree, statement.tree))
            for cluster in clusters
        ]
        marks.append(clusters[distances.index(min(distances))])
    return marks


# A statement of a bucket: the names of a call, drawn from four letters, so that the
# same tree comes up again and clusters keep a statement of their own as their pattern.
BUCKET = st.lists(
    st.lists(st.sampled_from("abcd"), min_size=1, max_size=3), min_size=1, max_size=12
)


@given(BUCKET, st.integers(0, 4))
def test_marking_agrees_with_weighing_every_cluster(names: list[list[str]], threshold: int) -> None:
    """A statement read off its pattern gets the mark weighing every cluster gives."""
    statements = [
        Statement(Node("Call", tuple(Node(name) for name in used), lines={line}), Path("x.py"))
        for line, used in enumerate(names, start=1)
    ]
    clusters = build_clusters(statements, threshold)
    gathered = [len(cluster) for cluster in clusters]
    expected = marks_by_weighing_every_cluster(statements, clusters)
    mark_statements(statements, clusters)
    assert [statement.mark for statement in statements] == expected
    assert [len(cluster) for cluster in clusters] == [
        count + expected.count(cluster) for count, cluster in zip(gathered, clusters, strict=True)
    ]


def test_a_statement_that_is_a_pattern_goes_to_the_first_cluster_holding_it() -> None:
    """Two clusters on the same pattern: the statement equal to it joins the first."""
    first = Cluster(Node("Add", (Node("a"), Node("b"))))
    second = Cluster(Node("Add", (Node("a"), Node("b"))))
    statement = Statement(Node("Add", (Node("a"), Node("b"))), Path("x.py"))
    mark_statements([statement], [first, second])
    assert statement.mark is first
    assert len(second) == 1


def test_a_cluster_without_a_pattern_keeps_the_statements_it_is_closest_to() -> None:
    """No pattern means a distance of zero: the clusters after it are not read off."""
    empty = Cluster()
    twin = Cluster(Node("Add", (Node("a"), Node("b"))))
    statement = Statement(Node("Add", (Node("a"), Node("b"))), Path("x.py"))
    mark_statements([statement], [Cluster(Node("Add", (Node("c"), Node("d")))), empty, twin])
    assert statement.mark is empty
