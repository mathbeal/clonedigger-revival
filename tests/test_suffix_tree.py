# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The suffix tree reports the pairs Clone Digger 1.1.0 reported."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clonedigger import SuffixTree

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
    assert tree.best_max_substrings(3, lambda _code: 2, len) == []
