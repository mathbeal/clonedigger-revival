# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, python_compiler.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: rewritten on the ast module)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read Python source into the trees and the statement sequences Clone Digger compares.

Clone Digger 1.1.0 read Python 2 with the `compiler` module, removed in Python 3.0.
This front end reads Python 3 with `ast`, and keeps the choices of the original:

- every list of statements (a body, an `else`, a `finally`) is a node labelled
  `Stmt`, whose children are the statements;
- a name, an attribute and a constant end in a leaf that holds their text, so that
  two trees differ exactly where a name or a value differs;
- imports and docstrings are left out, and so are functions whose name starts with
  one of the given prefixes.

Two choices are new, for what Python 2 did not have. The annotations of a function's
parameters and return value are left out: two functions that do the same work with
different annotations are still clones. The type of a declared field is kept, since
it is all a declaration says. And a string standing alone as a statement is left out
wherever it is, not only first in a body: it documents a field or a step, it does not
run.
"""

from __future__ import annotations

import ast
import sys
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from clonedigger.tree import Node

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from clonedigger.anti_unification import Cluster

# Statements that never make a clone, as in Clone Digger 1.1.0.
IGNORED_STATEMENTS: Final = (ast.Import, ast.ImportFrom)

# Fields that are bookkeeping, not code.
SKIPPED_FIELDS: Final = frozenset({"type_comment", "type_params", "ctx", "kind"})

# The annotations of a signature, left out.
SIGNATURE_FIELDS: Final = {"arg": frozenset({"annotation"}), "FunctionDef": frozenset({"returns"})}
SIGNATURE_FIELDS["AsyncFunctionDef"] = SIGNATURE_FIELDS["FunctionDef"]

# The node that holds a list of statements, as the compiler module of Python 2 named it.
STATEMENTS_LABEL: Final = "Stmt"

# Expression contexts that turn a name or an attribute into an assignment target, labelled
# as the compiler module of Python 2 labelled them.
STORE_LABELS: Final = {"Name": "AssName", "Attribute": "AssAttr"}


@dataclass(eq=False)
class Statement:
    """One statement of a file: its tree, and where it sits.

    Two statements are equal only when they are the same one: equal trees in two
    places are two statements, the very thing a clone is made of.

    Attributes:
        tree: The statement as a tree, nested statements included.
        path: The file it comes from.
        ancestors: The statements it is nested in, innermost first.
        mark: The cluster it belongs to, once the detection has clustered it.
    """

    tree: Node
    path: Path
    ancestors: tuple[Statement, ...] = ()
    mark: Cluster | None = field(default=None, repr=False)

    _covered: frozenset[int] | None = field(default=None, init=False, repr=False)

    @property
    def covered_lines(self) -> frozenset[int]:
        """The source lines the statement spans, computed once."""
        if self._covered is None:
            self._covered = self.tree.covered_lines
        return self._covered


@dataclass(frozen=True)
class SourceFile:
    """A parsed file: its lines, and its runs of consecutive statements.

    Attributes:
        path: Where it was read from.
        lines: Its text, line by line.
        sequences: Every run of statements that sit side by side, nested ones included.
    """

    path: Path
    lines: tuple[str, ...]
    sequences: tuple[tuple[Statement, ...], ...]


_UNBUILT: Final = Node("")


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


class _Reader:
    """Walks one module and builds its trees and its statement sequences."""

    def __init__(self, path: Path, skipped_prefixes: Sequence[str]) -> None:
        """Prepare to read one module.

        Args:
            path: The file, recorded on every statement.
            skipped_prefixes: Prefixes of the function names to leave out.
        """
        self.path = path
        self.skipped_prefixes = tuple(skipped_prefixes)
        self.sequences: list[tuple[Statement, ...]] = []

    def kept(self, statement: ast.stmt) -> bool:
        """Tell whether a statement takes part in the comparison.

        Args:
            statement: The statement.

        Returns:
            False for an import, a lone string, or a function with a skipped prefix.
        """
        if isinstance(statement, IGNORED_STATEMENTS) or _is_docstring(statement):
            return False
        return not (
            isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            and statement.name.startswith(self.skipped_prefixes)
        )

    def body(self, statements: list[ast.stmt], ancestors: tuple[Statement, ...]) -> Node:
        """Build the `Stmt` node of a list of statements, and record its sequence.

        Args:
            statements: The statements of a body.
            ancestors: The statements the node is nested in, innermost first.

        Returns:
            The node, whose children are the trees of the kept statements.
        """
        sequence = [self.statement(item, ancestors) for item in statements if self.kept(item)]
        if sequence:
            self.sequences.append(tuple(sequence))
        return Node(STATEMENTS_LABEL, (item.tree for item in sequence))

    def statement(self, node: ast.stmt, ancestors: tuple[Statement, ...]) -> Statement:
        """Build one statement; the statements nested in it record their own sequences.

        Args:
            node: The statement.
            ancestors: The statements the node is nested in, innermost first.

        Returns:
            The statement.
        """
        # The statement must exist before its tree, since the statements nested in it
        # name it among their ancestors: it starts with an empty tree.
        statement = Statement(_UNBUILT, self.path, ancestors)  # pragma: no mutate
        statement.tree = self.tree(node, (statement, *ancestors))
        return statement

    def tree(self, node: ast.AST, ancestors: tuple[Statement, ...]) -> Node:
        """Build the tree of an expression, a statement, or any other node.

        Args:
            node: The node.
            ancestors: The statements the node is nested in, innermost first.

        Returns:
            The node, with its children in the order of the ast fields.
        """
        label = type(node).__name__
        if isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del)) and label in STORE_LABELS:
            label = STORE_LABELS[label]
        lines = [node.lineno] if isinstance(node, (ast.stmt, ast.expr)) else []
        return Node(label, self.children(node, ancestors), lines)

    def children(self, node: ast.AST, ancestors: tuple[Statement, ...]) -> Iterator[Node]:
        """Build the children of a node, field by field.

        Args:
            node: The node.
            ancestors: The statements the node is nested in, innermost first.

        Yields:
            A `Stmt` node for a list of statements, a tree or a leaf for anything else.
        """
        skipped = SKIPPED_FIELDS | SIGNATURE_FIELDS.get(type(node).__name__, frozenset())
        fields = ((name, value) for name, value in ast.iter_fields(node) if name not in skipped)
        for _, value in fields:
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                yield self.body(value, ancestors)
            elif isinstance(value, list):
                yield from (self.child(item, ancestors) for item in value)
            else:
                # No single field holds statements (only lists do), so the ancestors
                # passed here never reach a statement; they are passed for clarity.
                yield self.child(value, ancestors)  # pragma: no mutate

    def child(self, value: object, ancestors: tuple[Statement, ...]) -> Node:
        """Build one child: a tree for a node, a leaf holding the text of anything else.

        Args:
            value: The value of a field.
            ancestors: The statements the node is nested in, innermost first.

        Returns:
            The child.
        """
        if isinstance(value, ast.AST):
            return self.tree(value, ancestors)
        # A name, an attribute name, an operator's text, a constant: a leaf holds its text.
        # The same names come back thousands of times in a large code base: one shared
        # string each.
        return Node(sys.intern(repr(value)))


def read_source(path: Path, text: str, skipped_prefixes: Sequence[str] = ()) -> SourceFile:
    """Read Python source into statement sequences.

    Args:
        path: Where the source comes from, for the report.
        text: The source.
        skipped_prefixes: Functions whose name starts with one of these are left out,
            as `--func-prefixes` did in Clone Digger 1.1.0.

    Returns:
        The file, with every sequence of statements found in it.
    """
    # Python warns about what the analysed code does (an invalid escape, say), not
    # about the analysis: those warnings are the business of that code's own checks.
    with warnings.catch_warnings():
        # Only SyntaxWarning is raised while parsing; naming it keeps others visible.
        warnings.simplefilter("ignore", SyntaxWarning)  # pragma: no mutate
        module = ast.parse(text, filename=str(path))
    reader = _Reader(path, skipped_prefixes)
    reader.body(module.body, ())
    return SourceFile(path, tuple(text.splitlines()), tuple(reader.sequences))
