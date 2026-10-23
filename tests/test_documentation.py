# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The examples of the documents under docs/ print what is written under them.

A document that explains an algorithm with examples is only as good as its examples
are true: every `>>>` block of those documents is a doctest, run here.
"""

from __future__ import annotations

import doctest
from pathlib import Path

import pytest

DOCUMENTS = sorted((Path(__file__).parent.parent / "docs").glob("*.md"))
HOW_IT_WORKS = Path(__file__).parent.parent / "docs" / "how-it-works.md"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.name)
def test_every_example_prints_what_the_document_says(path: Path) -> None:
    """Each `>>>` example of the document gives exactly the output written under it."""
    failed, _ = doctest.testfile(str(path), module_relative=False)
    assert not failed, f"{path.name}: {failed} example(s) print something else"


def test_the_algorithm_is_explained_with_examples() -> None:
    """The page on anti-unification holds examples, so the test above checks something."""
    _, attempted = doctest.testfile(str(HOW_IT_WORKS), module_relative=False)
    assert attempted
