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
from clonedigger.anti_unification import substitution_size

GOLDEN = json.loads((Path(__file__).parent / "golden" / "anti_unification.json").read_text())


def tree(label: str, *children: Node) -> Node:
    """A node, written the way the reference script writes it."""
    return Node(label, children)


T = tree
CASES = {
    "rename_and_constant": (
        T("Assign", T("total"), T("Mult", T("prix"), T("1.2"))),
        T("Assign", T("remise"), T("Mult", T("prix"), T("0.9"))),
    ),
    "same_difference_twice": (T("Add", T("a"), T("a")), T("Add", T("b"), T("b"))),
    "two_differences": (T("Add", T("a"), T("a")), T("Add", T("b"), T("c"))),
    "identical": (T("Call", T("f"), T("x")), T("Call", T("f"), T("x"))),
    "different_shape": (T("Call", T("f"), T("x")), T("Call", T("f"), T("x"), T("y"))),
    "subtree_differs": (
        T("Return", T("Mult", T("a"), T("b"))),
        T("Return", T("Add", T("a"), T("b"))),
    ),
}


def show(node: Node) -> str:
    """Write a tree as the reference script does: every variable is VAR."""
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
def test_distance_is_symmetric(first: Node, second: Node) -> None:
    """Swapping the trees swaps the substitutions and keeps the distance."""
    assert anti_unify(first, second).distance == anti_unify(second, first).distance


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
    assert substitution_size({Variable(): Node("Mult", (Node("a"), Node("b")))}) == 1.5


class TestCluster:
    """Clusters keep the pattern of their statements, as in Clone Digger 1.1.0."""

    def test_starts_with_its_first_statement(self) -> None:
        """A cluster made from a statement has it as its only member and pattern."""
        first = Node("Assign", (Node("x"), Node("1")), lines={3})
        cluster = Cluster(first)
        assert len(cluster) == 1
        assert cluster.pattern == first
        assert cluster.max_covered_lines == 1

    def test_cost_counts_every_member(self) -> None:
        """What the pattern loses is paid once per member; the newcomer pays once."""
        cluster = Cluster(Node("Add", (Node("a"), Node("b"))))
        cluster.unify(Node("Add", (Node("a"), Node("c"))))
        newcomer = Node("Add", (Node("d"), Node("c")))
        # The pattern Add(a, X) loses "a" (1 - 0.5) and keeps X (0.5 - 0.5); the
        # newcomer brings "d" and "c" for those two holes: 0.5 + 0.5.
        assert cluster.add_cost(newcomer) == 2 * 0.5 + 1.0

    def test_unify_widens_the_pattern(self) -> None:
        """After unification the pattern fits both statements."""
        cluster = Cluster(Node("Add", (Node("a"), Node("b"))))
        cluster.unify(Node("Add", (Node("a"), Node("c"))))
        assert len(cluster) == 2
        assert cluster.pattern is not None
        assert show(cluster.pattern) == "Add(a, VAR)"

    def test_unify_does_not_count_lines(self) -> None:
        """Only add_without_unification tracks the largest statement, as in 1.1.0."""
        cluster = Cluster(Node("x", lines={1}))
        cluster.unify(Node("y", lines={1, 2, 3}))
        assert cluster.max_covered_lines == 1
        cluster.add_without_unification(Node("z", lines={1, 2, 3}))
        assert cluster.max_covered_lines == 3

    def test_without_a_tree_it_only_labels(self) -> None:
        """A cluster made without a statement has no pattern to compare with."""
        cluster = Cluster()
        assert cluster.pattern is None
        with pytest.raises(ValueError, match="no pattern"):
            cluster.add_cost(Node("x"))
        with pytest.raises(ValueError, match="no pattern"):
            cluster.unify(Node("x"))
