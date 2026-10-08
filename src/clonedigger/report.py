# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write the clones found: text for a reader, JSON for a program, SARIF for CI.

SARIF is the format code scanning tools read (GitHub code scanning among them): each
clone is a result on its first copy, with the second copy as a related location.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING, Final

from clonedigger import __version__
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
        # Forward slashes on every system: reports are compared and shared across them.
        return cls(PurePath(sequence[0].path).as_posix(), min(lines), max(lines))

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


def largest_first(clones: Sequence[Clone]) -> list[Clone]:
    """Order the clones by the number of lines of their first copy, largest first.

    Args:
        clones: The clones found.

    Returns:
        The same clones; equal sizes are ordered by the place of each copy.
    """
    return sorted(clones, key=_order)


def _order(clone: Clone) -> tuple[int, str, int, str, int]:
    """Give the key that sorts the clones.

    Args:
        clone: A clone.

    Returns:
        Minus its number of lines, then the path and first line of each copy.
    """
    # Largest first; then by place, so that the same clones always print in one order.
    first, second = Span.of(clone.first), Span.of(clone.second)
    return (-len(covered_lines(clone.first)), first.path, first.start, second.path, second.start)


def findings(clones: Sequence[Clone]) -> list[Finding]:
    """Locate the clones, largest first.

    Args:
        clones: The clones found.

    Returns:
        One finding per clone, in the order of `largest_first`.
    """
    return [
        Finding(Span.of(clone.first), Span.of(clone.second), clone.distance)
        for clone in largest_first(clones)
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


# The one rule this tool checks, as SARIF describes rules.
RULE_ID: Final = "duplicated-code"
SARIF_SCHEMA: Final = "https://json.schemastore.org/sarif-2.1.0.json"
ORIGINAL_URI: Final = "http://clonedigger.sourceforge.net"


def _location(span: Span) -> dict[str, object]:
    """Write where a copy lies, as SARIF describes a location.

    Args:
        span: The copy.

    Returns:
        A SARIF `location`: its file and its first and last lines.
    """
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": span.path},
            "region": {"startLine": span.start, "endLine": span.end},
        }
    }


def as_sarif(clones: Sequence[Clone]) -> str:
    """Write the clones as a SARIF 2.1.0 log.

    Args:
        clones: The clones found.

    Returns:
        One run of this tool, with one result per clone: located on its first copy,
        with the second copy as a related location, so that each copy is reported once
        per pair.
    """
    results = [
        {
            "ruleId": RULE_ID,
            "level": "warning",
            "message": {
                "text": (
                    f"Lines {finding.first.start}-{finding.first.end} are a copy of "
                    f"[{finding.second}](1), up to a difference of {finding.distance:g}."
                )
            },
            "locations": [_location(finding.first)],
            "relatedLocations": [
                {"id": 1, "message": {"text": "the other copy"}, **_location(finding.second)}
            ],
        }
        for finding in findings(clones)
    ]
    rule = {
        "id": RULE_ID,
        "name": "DuplicatedCode",
        "shortDescription": {"text": "Two runs of statements are copies of one another."},
        "fullDescription": {
            "text": (
                "Found by anti-unification: the two copies have the same shape and differ "
                "only in a few names, constants or subtrees."
            )
        },
        "defaultConfiguration": {"level": "warning"},
    }
    driver = {
        "name": "clonedigger",
        "version": __version__,
        "informationUri": ORIGINAL_URI,
        "rules": [rule],
    }
    log = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [{"tool": {"driver": driver}, "results": results}],
    }
    return json.dumps(log, indent=2)
