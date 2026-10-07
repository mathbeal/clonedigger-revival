# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Python source becomes the trees and the statement sequences Clone Digger compares."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from clonedigger.python_frontend import STATEMENTS_LABEL, read_source

HERE = Path("example.py")


def labels(text: str) -> list[list[str]]:
    """Read source and list, for each sequence, the label of each statement.

    Returns:
        One list of labels per sequence, in the order they were found.
    """
    source = read_source(HERE, dedent(text))
    return [[statement.tree.label for statement in sequence] for sequence in source.sequences]


def test_every_body_is_a_sequence() -> None:
    """A module, a function body and an else branch each make a sequence."""
    found = labels(
        """
        x = 1
        def f():
            if x:
                y = 2
            else:
                y = 3
            return y
        """
    )
    assert ["Assign", "FunctionDef"] in found
    assert ["If", "Return"] in found
    assert found.count(["AssName"]) == 0
    assert found.count(["Assign"]) == 2


def test_imports_and_docstrings_are_left_out() -> None:
    """Imports and strings standing alone as statements make no statement."""
    found = labels(
        '''
        """Module docstring."""
        import os
        from sys import path
        class Model:
            name: str
            """The name."""
            size: int
            """The size."""
        '''
    )
    assert sorted(found) == [["AnnAssign", "AnnAssign"], ["ClassDef"]]


def test_functions_with_a_skipped_prefix_are_left_out() -> None:
    """A function whose name starts with a given prefix is not read."""
    source = read_source(HERE, "def test_a():\n    pass\ndef b():\n    pass\n", ("test_",))
    module = source.sequences[-1]
    assert [statement.tree.children[0].label for statement in module] == ["'b'"]


def test_names_and_constants_end_in_leaves() -> None:
    """A name holds its text in a leaf, and so does a constant."""
    (sequence,) = read_source(HERE, "total = 1.2\n").sequences
    assert repr(sequence[0].tree) == "Assign(AssName('total'), Constant(1.2))"


def test_signature_annotations_are_left_out_but_field_types_kept() -> None:
    """Parameter and return annotations vanish; a declared field keeps its type."""
    annotated = read_source(HERE, "def f(a: int) -> str:\n    return a\n").sequences[0][0]
    bare = read_source(HERE, "def f(a):\n    return a\n").sequences[0][0]
    assert annotated.tree == bare.tree
    field = read_source(HERE, "size: int\n").sequences[0][0]
    assert "Name('int')" in repr(field.tree)


def test_targets_are_labelled_as_assignments() -> None:
    """A name or an attribute being assigned is labelled as Python 2 did."""
    (sequence,) = read_source(HERE, "a.b = c\n").sequences
    assert repr(sequence[0].tree) == "Assign(AssAttr(Name('a'), 'b'), Name('c'))"


def test_statements_know_where_they_sit() -> None:
    """A nested statement lists the statements around it, innermost first."""
    source = read_source(HERE, "def f():\n    for x in y:\n        z = x\n")
    inner = next(seq for seq in source.sequences if seq[0].tree.label == "Assign")[0]
    assert [ancestor.tree.label for ancestor in inner.ancestors] == ["For", "FunctionDef"]
    assert inner.covered_lines == {3}
    assert inner.path == HERE


def test_lines_are_kept() -> None:
    """The file's text is kept line by line, for reports."""
    assert read_source(HERE, "a = 1\nb = 2\n").lines == ("a = 1", "b = 2")


def test_statements_are_distinct_even_when_equal() -> None:
    """Two equal statements in two places are two statements."""
    first, second = read_source(HERE, "a = 1\na = 1\n").sequences[0]
    assert first.tree == second.tree
    assert first != second


def test_warnings_of_the_analysed_code_are_not_raised() -> None:
    """An invalid escape in the code read is that code's problem, not a warning here."""
    (sequence,) = read_source(HERE, 'pattern = "\\S"\n').sequences
    assert sequence[0].tree.label == "Assign"


def test_lists_of_statements_keep_the_original_label() -> None:
    """A body is a Stmt node, as the compiler module of Python 2 named it."""
    assert STATEMENTS_LABEL == "Stmt"
    (function,) = read_source(HERE, "def f():\n    return 1\n").sequences[-1]
    assert [child.label for child in function.tree.children] == ["'f'", "arguments", "Stmt"]


def test_other_targets_keep_their_own_label() -> None:
    """A subscript being assigned keeps its label: only names and attributes change."""
    (sequence,) = read_source(HERE, "a[0] = 1\n").sequences
    assert sequence[0].tree.children[0].label == "Subscript"


def test_statements_inside_a_handler_know_where_they_sit() -> None:
    """A statement in an except clause lists the try statement among its ancestors."""
    source = read_source(HERE, "try:\n    a = 1\nexcept ValueError:\n    b = 2\n")
    handled = next(seq for seq in source.sequences if 4 in seq[0].covered_lines)[0]
    assert [ancestor.tree.label for ancestor in handled.ancestors] == ["Try"]


def test_a_file_remembers_its_path() -> None:
    """The parsed file keeps the path it was read from."""
    assert read_source(HERE, "a = 1\n").path == HERE


def test_syntax_errors_name_the_file() -> None:
    """A file that does not parse is named in the error."""
    with pytest.raises(SyntaxError) as error:
        read_source(HERE, "def (:\n")
    assert error.value.filename == str(HERE)
