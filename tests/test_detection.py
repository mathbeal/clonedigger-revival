# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pipeline finds the clones Clone Digger 1.1.0 found, and only those."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

import pytest

from clonedigger.anti_unification import Cluster
from clonedigger.detection import (
    MAX_EQUAL_MARKS,
    Clone,
    Settings,
    dcup_hash,
    drop_long_equal_runs,
    find_clones,
    mark_statements,
    refine,
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
