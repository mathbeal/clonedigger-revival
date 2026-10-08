# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every function, method and class has a docstring, private and nested ones included.

ruff checks the docstrings of public names only, and pydoclint checks the sections of
the docstrings that exist: neither notices a private function with none. The Google
style guide asks for one on any function that is not both short and obvious; here,
on every one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCES = [
    path
    for directory in ("src/clonedigger", "tests", "benchmarks")
    for path in sorted((ROOT / directory).glob("*.py"))
]
DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: path.name)
def test_every_definition_has_a_docstring(path: Path) -> None:
    """No function, method or class of the file goes without a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = [
        f"{node.name} (line {node.lineno})"
        for node in ast.walk(tree)
        if isinstance(node, DEFINITIONS) and not ast.get_docstring(node)
    ]
    assert not missing, f"{path.name}: no docstring for {', '.join(missing)}"
