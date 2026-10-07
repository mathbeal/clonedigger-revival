# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The suffix tree reports the pairs Clone Digger 1.1.0 reported."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from clonedigger import SuffixTree

if TYPE_CHECKING:
    from collections.abc import Sequence

GOLDEN = json.loads((Path(__file__).parent / "golden" / "suffix_tree.json").read_text())


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_matches_clone_digger_1_1_0(name: str) -> None:
    """Same words, same threshold: the same pairs, whatever their order."""
    case = GOLDEN[name]
    tree: SuffixTree[str] = SuffixTree(lambda element: element)
    for word in case["words"]:
        tree.add(list(word))
    pairs = tree.best_max_substrings(case["threshold"], lambda _code: 1, len)
    assert sorted(sorted(["".join(a), "".join(b)]) for a, b in pairs) == case["pairs"]


def test_codes_decide_what_matches() -> None:
    """Elements match on their code, not on their value."""
    tree: SuffixTree[str] = SuffixTree(str.lower)
    tree.add(list("xABCy"))
    tree.add(list("zabcw"))
    pairs = tree.best_max_substrings(3, lambda _code: 1, len)
    assert sorted(sorted(["".join(a), "".join(b)]) for a, b in pairs) == [["ABC", "abc"]]


def test_light_candidates_are_dropped() -> None:
    """A run heavy enough by weight but too small by size is not reported."""
    tree: SuffixTree[str] = SuffixTree(lambda element: element)
    tree.add(list("xaby"))
    tree.add(list("zabw"))
    assert not tree.best_max_substrings(3, lambda _code: 2, len)


def _run_pairs(tree: SuffixTree[str], *args: object) -> list[list[str]]:
    """Run the search and write its pairs as sorted strings.

    Returns:
        Each pair as two strings, the pairs sorted.
    """
    pairs = tree.best_max_substrings(*args)  # type: ignore[arg-type]
    return sorted(sorted(["".join(a), "".join(b)]) for a, b in pairs)


@pytest.mark.parametrize("words", [("xABy", "zabw"), ("zabw", "xABy")])
def test_one_side_reaching_the_threshold_is_enough(words: tuple[str, str]) -> None:
    """A pair is kept when either side, not both, reaches the threshold, equality included."""
    tree: SuffixTree[str] = SuffixTree(str.lower)
    for word in words:
        tree.add(list(word))

    def capitals_count(run: Sequence[str]) -> float:
        return sum(1 if element.isupper() else 0.25 for element in run)

    # "AB" weighs exactly 2, "ab" only 0.5: the pair stands on its heavier side.
    assert _run_pairs(tree, 2, lambda _code: 1, capitals_count) == [["AB", "ab"]]


def test_the_search_stops_where_the_weight_runs_out() -> None:
    """Runs are looked for only once the path has used up the threshold."""
    tree: SuffixTree[str] = SuffixTree(lambda element: element)
    tree.add(list("xaby"))
    tree.add(list("zabw"))
    # Every run passes the size test; only the weight along the path decides.
    assert _run_pairs(tree, 2, lambda _code: 1, lambda _run: 10) == [["ab", "ab"]]
    assert _run_pairs(tree, 3, lambda _code: 1, lambda _run: 10) == []


def test_weight_depends_on_the_code() -> None:
    """Each element weighs what its code weighs."""
    tree: SuffixTree[str] = SuffixTree(lambda element: element)
    tree.add(list("xaby"))
    tree.add(list("zabw"))
    heavy_a = {"a": 3}
    # "a" alone uses up the threshold, so the search starts one level higher than with
    # equal weights, where nothing would reach 3 before the strings part.
    assert _run_pairs(tree, 3, lambda code: heavy_a.get(str(code), 1), lambda _run: 10) == [
        ["ab", "ab"]
    ]
    assert _run_pairs(tree, 3, lambda _code: 1, lambda _run: 10) == []
