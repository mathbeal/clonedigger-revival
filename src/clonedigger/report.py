# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write the clones found, as text for a reader or JSON for a program.

The HTML report of Clone Digger 1.1.0 is not ported yet.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from clonedigger.detection import covered_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

    from clonedigger.detection import Clone
    from clonedigger.python_frontend import Statement


@dataclass(frozen=True)
class Span:
    """Where one copy lies: a file and its first and last line.

    Attributes:
        path: The file.
        start: The first line, counted from 1.
        end: The last line.
    """

    path: str
    start: int
    end: int

    @classmethod
    def of(cls, sequence: Sequence[Statement]) -> Span:
        """Locate a run of statements.

        Args:
            sequence: The statements, all from one file.

        Returns:
            Their file and the lines they span.
        """
        lines = covered_lines(sequence)
        return cls(str(sequence[0].path), min(lines), max(lines))

    def __str__(self) -> str:
        """Write the span as path:start-end.

        Returns:
            The span, as a reader expects it.
        """
        return f"{self.path}:{self.start}-{self.end}"


@dataclass(frozen=True)
class Finding:
    """A clone as reported: its two copies and how much they differ.

    Attributes:
        first: One copy.
        second: The other.
        distance: Their anti-unification distance.
    """

    first: Span
    second: Span
    distance: float


def findings(clones: Sequence[Clone]) -> list[Finding]:
    """Locate the clones, largest first.

    Args:
        clones: The clones found.

    Returns:
        One finding per clone, ordered by the number of lines of its first copy.
    """
    ordered = sorted(clones, key=lambda clone: -len(covered_lines(clone.first)))
    return [
        Finding(Span.of(clone.first), Span.of(clone.second), clone.distance) for clone in ordered
    ]


def as_json(clones: Sequence[Clone]) -> str:
    """Write the clones as JSON.

    Args:
        clones: The clones found.

    Returns:
        A JSON array of findings, each with `first`, `second` and `distance`.
    """
    return json.dumps([asdict(finding) for finding in findings(clones)], indent=2)


def as_text(clones: Sequence[Clone]) -> str:
    """Write the clones one per line, for a reader.

    Args:
        clones: The clones found.

    Returns:
        A line per clone, then a count.
    """
    lines = [
        f"{finding.first}  ~  {finding.second}  (distance {finding.distance:g})"
        for finding in findings(clones)
    ]
    lines.append(f"{len(clones)} clone{'' if len(clones) == 1 else 's'} found.")
    return "\n".join(lines)
