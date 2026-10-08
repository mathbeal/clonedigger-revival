# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Anti-unification gives the answers of Clone Digger 1.1.0, and keeps its promises."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from clonedigger import Cluster, Node, Variable, anti_unify, substitute
from clonedigger.anti_unification import difference, substitution_size

GOLDEN = json.loads((Path(__file__).parent / "golden" / "anti_unification.json").read_text())


def tree(label: str, *children: Node) -> Node:
    """Build a node the way the reference script writes it.

    Args:
        label: The node's label.
        *children: Its children, in order.

    Returns:
        The node.
    """
    return Node(label, children)


CASES = {
    "rename_and_constant": (
        tree("Assign", tree("total"), tree("Mult", tree("prix"), tree("1.2"))),
        tree("Assign", tree("remise"), tree("Mult", tree("prix"), tree("0.9"))),
    ),
    "same_difference_twice": (tree("Add", tree("a"), tree("a")), tree("Add", tree("b"), tree("b"))),
    "two_differences": (tree("Add", tree("a"), tree("a")), tree("Add", tree("b"), tree("c"))),
    "identical": (tree("Call", tree("f"), tree("x")), tree("Call", tree("f"), tree("x"))),
    "different_shape": (
        tree("Call", tree("f"), tree("x")),
        tree("Call", tree("f"), tree("x"), tree("y")),
    ),
    "subtree_differs": (
        tree("Return", tree("Mult", tree("a"), tree("b"))),
        tree("Return", tree("Add", tree("a"), tree("b"))),
    ),
}


def show(node: Node) -> str:
    """Write a tree as the reference script does.

    Args:
        node: The tree.

    Returns:
        The tree as text, every variable written VAR.
    """
    if isinstance(node, Variable):
        return "VAR"
    if node.is_leaf:
        return node.label
    return f"{node.label}({', '.join(show(child) for child in node.children)})"


@pytest.mark.parametrize("name", sorted(CASES))
def test_matches_clone_digger_1_1_0(name: str) -> None:
    """Pattern, variables, sizes and distance are those the original release computed."""
    expected = GOLDEN[name]
    result = anti_unify(*CASES[name])
    assert show(result.pattern) == expected["pattern"]
    assert result.variables == expected["variables"]
    assert [result.left_size, result.right_size] == expected["substitution_sizes"]
    assert result.distance == expected["distance"]
    assert [
        sorted(show(value) for value in result.left.values()),
        sorted(show(value) for value in result.right.values()),
    ] == expected["substitutions"]


def test_every_golden_case_is_checked() -> None:
    """No case recorded from the original is left without a test."""
    assert set(CASES) == set(GOLDEN)


def test_variables_can_stay_apart() -> None:
    """Without sharing, the same difference met twice makes two variables."""
    first, second = CASES["same_difference_twice"]
    assert anti_unify(first, second, share_variables=False).variables == 2


LABELS = st.sampled_from(["Add", "Mult", "Call", "Assign"])
LEAVES = st.sampled_from(["a", "b", "x", "1", "2"]).map(Node)
TREES = st.recursive(
    LEAVES,
    lambda children: st.builds(Node, LABELS, st.lists(children, min_size=1, max_size=3)),
    max_leaves=12,
)


@given(TREES, TREES)
def test_each_substitution_gives_back_its_tree(first: Node, second: Node) -> None:
    """Filling the pattern's holes from one side rebuilds that side exactly."""
    result = anti_unify(first, second)
    assert substitute(result.pattern, result.left) == first
    assert substitute(result.pattern, result.right) == second


@given(TREES)
def test_a_tree_and_itself_have_no_difference(node: Node) -> None:
    """A tree anti-unified with itself is its own pattern, at distance zero."""
    result = anti_unify(node, node)
    assert result.pattern == node
    assert result.variables == 0
    assert result.distance == 0


@given(TREES, TREES)
def test_distance_is_symmetric(one: Node, other: Node) -> None:
    """Swapping the trees swaps the substitutions and keeps the distance."""
    assert anti_unify(one, other).distance == anti_unify(other, one).distance


@given(TREES, TREES)
def test_sharing_never_makes_more_variables(first: Node, second: Node) -> None:
    """Sharing variables gives a pattern at least as specific as not sharing them."""
    shared = anti_unify(first, second)
    apart = anti_unify(first, second, share_variables=False)
    assert shared.variables <= apart.variables


def test_substitute_leaves_unknown_variables_alone() -> None:
    """A variable the substitution does not mention stays a hole."""
    hole = Variable()
    pattern = Node("Add", (hole, Node("a")))
    assert substitute(pattern, {}) == pattern


def test_a_substitution_weighs_what_it_replaces_less_its_holes() -> None:
    """Two distinct leaves replaced by one variable weigh 2 - 0.5."""
    assert substitution_size({Variable(): Node("Mult", (Node("a"), Node("b")))}) == pytest.approx(
        1.5
    )


def test_cluster_starts_with_its_first_statement() -> None:
    """A cluster made from a statement has it as its only member and pattern."""
    first = Node("Assign", (Node("x"), Node("1")), lines={3})
    cluster = Cluster(first)
    assert len(cluster) == 1
    assert cluster.pattern == first
    assert cluster.max_covered_lines == 1


def test_cluster_cost_counts_every_member() -> None:
    """What the pattern loses is paid once per member; the newcomer pays once."""
    cluster = Cluster(Node("Add", (Node("a"), Node("b"))))
    cluster.unify(Node("Add", (Node("a"), Node("c"))))
    newcomer = Node("Add", (Node("d"), Node("c")))
    # The pattern Add(a, X) loses "a" (1 - 0.5) and keeps X (0.5 - 0.5); the
    # newcomer brings "d" and "c" for those two holes: 0.5 + 0.5.
    assert cluster.add_cost(newcomer) == pytest.approx(2 * 0.5 + 1.0)


def test_cluster_unify_widens_the_pattern() -> None:
    """After unification the pattern fits both statements."""
    cluster = Cluster(Node("Add", (Node("a"), Node("b"))))
    cluster.unify(Node("Add", (Node("a"), Node("c"))))
    assert len(cluster) == 2
    assert cluster.pattern is not None
    assert show(cluster.pattern) == "Add(a, VAR)"


def test_cluster_unify_does_not_count_lines() -> None:
    """Only add_without_unification tracks the largest statement, as in 1.1.0."""
    cluster = Cluster(Node("x", lines={1}))
    cluster.unify(Node("y", lines={1, 2, 3}))
    assert cluster.max_covered_lines == 1
    cluster.add_without_unification(Node("z", lines={1, 2, 3}))
    assert cluster.max_covered_lines == 3


def test_cluster_without_a_tree_it_only_labels() -> None:
    """A cluster made without a statement has no pattern to compare with."""
    cluster = Cluster()
    assert cluster.pattern is None
    with pytest.raises(
        ValueError, match=r"^a cluster made without a tree has no pattern to (compare with|widen)$"
    ):
        cluster.add_cost(Node("x"))
    with pytest.raises(
        ValueError, match=r"^a cluster made without a tree has no pattern to (compare with|widen)$"
    ):
        cluster.unify(Node("x"))


def test_cluster_keeps_its_statements_in_order() -> None:
    """Every statement added, unified or not, is kept, in the order it came."""
    first, second, third = Node("x"), Node("y"), Node("z")
    cluster = Cluster(first)
    cluster.unify(second)
    cluster.add_without_unification(third)
    assert cluster.trees == [first, second, third]


def test_cluster_without_statement_covers_no_line() -> None:
    """An empty cluster has covered no line yet."""
    assert Cluster().max_covered_lines == 0


def test_patterns_keep_the_lines_of_the_first_tree() -> None:
    """The pattern and a rebuilt tree point to the source lines of the first tree."""
    first = Node("Add", (Node("a", lines={2}), Node("b")), lines={1})
    second = Node("Add", (Node("a", lines={8}), Node("c")), lines={7})
    result = anti_unify(first, second)
    assert result.pattern.lines == {1}
    assert substitute(result.pattern, result.left).covered_lines == {1, 2}


@given(TREES, TREES)
def test_difference_weighs_what_anti_unification_would(one: Node, other: Node) -> None:
    """The quick weighing gives the sizes of the full anti-unification, exactly."""
    result = anti_unify(one, other)
    assert difference(one, other) == (result.left_size, result.right_size)


@pytest.mark.parametrize("name", sorted(CASES))
def test_difference_on_the_recorded_cases(name: str) -> None:
    """The quick weighing matches the sizes Clone Digger 1.1.0 recorded."""
    assert list(difference(*CASES[name])) == GOLDEN[name]["substitution_sizes"]


@given(TREES, TREES, st.integers(min_value=0, max_value=12))
def test_difference_stops_at_its_limit(one: Node, other: Node, limit: int) -> None:
    """Under the limit the sizes are exact; at it or over, their sum has reached it."""
    exact = sum(difference(one, other))
    bounded = sum(difference(one, other, limit))
    if exact < limit:
        assert bounded == exact
    else:
        assert limit <= bounded <= exact


@given(TREES, TREES, st.integers(min_value=0, max_value=12))
def test_add_cost_is_exact_below_its_limit(one: Node, other: Node, limit: int) -> None:
    """Below the limit, the cost is the full one; otherwise it reaches the limit."""
    cluster = Cluster(one)
    cluster.unify(one)
    exact = cluster.add_cost(other)
    bounded = cluster.add_cost(other, limit)
    if exact < limit:
        assert bounded == exact
    else:
        assert bounded >= limit


def test_difference_stops_at_the_first_difference_that_reaches_the_limit() -> None:
    """With ten differences and a limit of one, the walk stops after the first."""
    one = Node("Call", tuple(Node(f"a{index}") for index in range(10)))
    other = Node("Call", tuple(Node(f"b{index}") for index in range(10)))
    assert sum(difference(one, other)) == 10
    assert difference(one, other, 1) == (0.5, 0.5)
    assert difference(one, other, 1.5) == (1.0, 1.0)
