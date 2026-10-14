# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Measure precision on the labelled sample: how many reported pairs are real copies.

Precision is the share of the pairs reported that are duplicated code to a reader. It is
measured on a sample drawn at random from the pairs of two pinned projects, judged one by
one with `just label` against the criteria written in docs/precision.md.

A share measured on a sample is not the share of the whole, so every figure comes with
its Wilson 95 % interval, and every share is rounded away from the tool's advantage: the
precision and the lower bound down, the upper bound up. The exact count is printed next
to it, so nothing is hidden by the rounding.

Under the table come the counts that say what the figure is made of: how many pairs each
criterion of docs/precision.md decided, and which reasons were given to more than one
pair. Both are read from the verdicts, which is why a reason begins with the number of
the criterion that decided it.

The pairs drawn are in benchmarks/sample.json, the verdicts in benchmarks/labels.jsonl,
both committed: this reads those two files only, with no network and no Docker.

Run it with `just precision`; `just sample` draws the pairs again.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from benchmarks.label import read_labels, read_pairs
from clonedigger.report import Span

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import TextIO

    from benchmarks.label import Label

# The two copies of one reported pair, as the report wrote them.
Pair = tuple[Span, Span]
# The confidence of the interval printed beside every share.
CONFIDENCE: Final = 0.95
# Strings, which argparse turns into paths: written with forward slashes, the help reads
# the same on every system.
DEFAULT_SAMPLE: Final = "benchmarks/sample.json"
DEFAULT_LABELS: Final = "benchmarks/labels.jsonl"
# The headings of the table, and the columns the first one is given.
HEADINGS: Final = ("pairs", "duplicated code", "precision", "95 % Wilson")
NAME_WIDTH: Final = 34
# What the two counts under the table are called.
BY_CRITERION: Final = "the criterion each verdict was decided on:"
RECURRING: Final = "the reasons given to more than one pair:"
# The number of the criterion a reason begins with, as `just label` records it.
NUMBERED: Final = re.compile(r"^(\d+): ")
# A reason given to fewer pairs than this is a pair of its own, not a family.
TWICE: Final = 2


def _place(pair: Pair) -> tuple[str, int, int, str, int, int]:
    """Name where a pair lies, as an order that does not depend on the report.

    Args:
        pair: The two copies.

    Returns:
        The path and lines of one copy, then of the other.
    """
    first, second = pair
    return (first.path, first.start, first.end, second.path, second.start, second.end)


def draw(pairs: Sequence[Pair], size: int, seed: int) -> list[Pair]:
    """Draw a sample of the pairs reported, the same sample at every run.

    Args:
        pairs: The pairs reported, in any order.
        size: How many pairs to draw.
        seed: The seed written down, which is what makes the draw repeatable.

    Returns:
        The pairs drawn, in the order the draw gives them.

    Raises:
        ValueError: Fewer pairs were reported than the size asked for.
    """
    if len(pairs) < size:
        msg = f"{len(pairs)} pairs reported, {size} asked for"
        raise ValueError(msg)
    # Ordered by where they lie first: the draw then depends on the pairs reported, not
    # on the order the report happened to list them in.
    # A sample of code to read, not a secret: the point is that it can be drawn again.
    return random.Random(seed).sample(  # ruff: ignore[suspicious-non-cryptographic-random-usage]
        sorted(pairs, key=_place), size
    )


def wilson(clones: int, pairs: int, confidence: float = CONFIDENCE) -> tuple[float, float]:
    """Bound the precision a sample was drawn from (Wilson score interval).

    The textbook interval, the share plus or minus a multiple of its standard error, is
    wrong for a share near 0 or 1 and can leave the 0..1 range. The Wilson interval holds
    the shares whose own standard error reaches the share measured, which does not.

    Args:
        clones: How many pairs of the sample are duplicated code.
        pairs: How many pairs the sample holds.
        confidence: The confidence of the interval, 0.95 for 95 %.

    Returns:
        The lowest and the highest share, each between 0 and 1.

    Raises:
        ValueError: The sample is empty, or holds fewer pairs than it has clones.
    """
    if pairs < 1:
        msg = "an empty sample says nothing about precision"
        raise ValueError(msg)
    if not 0 <= clones <= pairs:
        msg = f"{clones} of {pairs} pairs cannot be duplicated code"
        raise ValueError(msg)
    spread = statistics.NormalDist().inv_cdf((1 + confidence) / 2)
    weight = spread**2
    middle = (clones + weight / 2) / (pairs + weight)
    reach = spread * math.sqrt(clones * (pairs - clones) / pairs + weight / 4) / (pairs + weight)
    # With no clone the reach is the middle, bit for bit, so the low bound is 0 and needs
    # no help. With nothing but clones the high bound can land one step above 1 (33 pairs
    # out of 33 does), and a share above 1 would be written as 100.1 %.
    return (middle - reach, min(1.0, middle + reach))


@dataclass(frozen=True)
class Measure:
    """Precision over one set of the pairs drawn.

    Attributes:
        name: What those pairs have in common.
        pairs: How many there are.
        clones: How many of them are duplicated code.
    """

    name: str
    pairs: int
    clones: int

    @property
    def precision(self) -> float:
        """Read the share of the pairs that are duplicated code.

        Returns:
            The share, between 0 and 1.
        """
        return self.clones / self.pairs

    def row(self) -> str:
        """Write the measure as one row of the table.

        Returns:
            Its name, its counts, its precision and its interval, in columns.
        """
        low, high = wilson(self.clones, self.pairs)
        return (
            f"{self.name:<{NAME_WIDTH}}{self.pairs:>5}{self.clones:>16}"
            f"{down(self.precision):>11}  [{down(low)}, {up(high)}]"
        )


def down(share: float) -> str:
    """Write a share as a percentage, rounded down.

    Args:
        share: The share, between 0 and 1.

    Returns:
        The percentage to one decimal, never above the share.
    """
    return f"{math.floor(share * 1000) / 10:.1f} %"


def up(share: float) -> str:
    """Write a share as a percentage, rounded up.

    Args:
        share: The share, between 0 and 1.

    Returns:
        The percentage to one decimal, never below the share.
    """
    return f"{math.ceil(share * 1000) / 10:.1f} %"


def project(pair: Pair) -> str:
    """Name the release a pair was found in.

    Args:
        pair: The two copies.

    Returns:
        The first part of the path of its first copy, which is the directory of the
        pinned release the sample was drawn from.
    """
    return PurePosixPath(pair[0].path).parts[0]


def overlapping(pair: Pair) -> bool:
    """Say whether the two copies of a pair share lines.

    In a run of similar statements, a window and the same window shifted can both be
    reported, as 1.1.0 did; whether they should be is still open (ROADMAP.md).

    Args:
        pair: The two copies.

    Returns:
        True when both lie in the same file and their lines meet.
    """
    first, second = pair
    return first.path == second.path and first.start <= second.end and second.start <= first.end


def criterion(label: Label) -> int:
    """Read the criterion a verdict was decided on.

    Args:
        label: The verdict. Its reason begins with the number of the criterion of
            docs/precision.md that decided it, then a colon: that is what lets the
            counts by criterion be made again from the file.

    Returns:
        That number.

    Raises:
        ValueError: The reason does not begin with a criterion number and a colon.
    """
    found = NUMBERED.match(label.reason)
    if found is None:
        msg = (
            f"{label.first} ~ {label.second}: the reason must begin with the number of "
            f'the criterion that decided it, as in "4: locale table", not "{label.reason}"'
        )
        raise ValueError(msg)
    return int(found[1])


def verdicts(sample: Sequence[Pair], labels: Iterable[Label]) -> dict[Pair, Label]:
    """Match the verdicts recorded to the pairs drawn.

    Args:
        sample: The pairs drawn.
        labels: Every verdict recorded, of this sample or of another report.

    Returns:
        The verdict of each pair of the sample.

    Raises:
        ValueError: A pair of the sample was judged twice, or not judged at all.
    """
    wanted = set(sample)
    given: dict[Pair, Label] = {}
    for label in labels:
        if label.pair not in wanted:
            continue
        if label.pair in given:
            msg = f"{label.first} ~ {label.second}: judged twice"
            raise ValueError(msg)
        given[label.pair] = label
    left = [pair for pair in sample if pair not in given]
    if left:
        first, second = left[0]
        msg = f"{len(left)} pairs of the sample not judged yet, the first {first} ~ {second}"
        raise ValueError(msg)
    return given


def _over(name: str, pairs: Iterable[Pair], given: dict[Pair, Label]) -> Measure:
    """Measure precision over some of the pairs drawn.

    Args:
        name: What those pairs have in common.
        pairs: The pairs.
        given: The verdict of each pair of the sample.

    Returns:
        The measure over them.
    """
    chosen = list(pairs)
    return Measure(name, len(chosen), sum(1 for pair in chosen if given[pair].clone))


def measures(sample: Sequence[Pair], given: dict[Pair, Label]) -> list[Measure]:
    """Measure precision over the whole sample and over the parts worth reading apart.

    Args:
        sample: The pairs drawn.
        given: The verdict of each of them.

    Returns:
        One measure per release, then the whole sample, then the pairs whose two copies
        share lines and the sample without them.
    """
    parts = [
        _over(name, [pair for pair in sample if project(pair) == name], given)
        for name in sorted({project(pair) for pair in sample})
    ]
    parts.append(_over("the whole sample", sample, given))
    overlap = [pair for pair in sample if overlapping(pair)]
    apart = [pair for pair in sample if not overlapping(pair)]
    # Nothing to split when every pair of the sample falls on one side of the split.
    if overlap and apart:
        parts.extend(
            (
                _over("their copies overlap", overlap, given),
                _over("the sample without them", apart, given),
            )
        )
    return parts


def table(parts: Sequence[Measure]) -> str:
    """Write the measures as a table.

    Args:
        parts: The measures, in the order they are shown.

    Returns:
        The headings and one row per measure.
    """
    headings = (
        f"{'':<{NAME_WIDTH}}{HEADINGS[0]:>5}{HEADINGS[1]:>16}{HEADINGS[2]:>11}  {HEADINGS[3]}"
    )
    return "\n".join([headings, *(part.row() for part in parts)])


def criteria(sample: Sequence[Pair], given: dict[Pair, Label]) -> str:
    """Count the pairs drawn by the criterion their verdict was decided on.

    Args:
        sample: The pairs drawn.
        given: The verdict of each of them.

    Returns:
        One line per criterion met: its number, how many pairs it decided, and whether
        it counts them as duplicated code.

    Raises:
        ValueError: One criterion decided both ways, which means a verdict was recorded
            under the wrong number.
    """
    lines = []
    for number in sorted({criterion(given[pair]) for pair in sample}):
        decided = [pair for pair in sample if criterion(given[pair]) == number]
        clones = sum(1 for pair in decided if given[pair].clone)
        if clones not in {0, len(decided)}:
            msg = (
                f"criterion {number} decided both ways, {clones} of {len(decided)} pairs "
                f"duplicated code: a verdict is recorded under the wrong number"
            )
            raise ValueError(msg)
        what = "duplicated code" if clones else "not duplicated code"
        lines.append(f"{f'criterion {number}':<{NAME_WIDTH}}{len(decided):>5}  {what}")
    return "\n".join(lines)


def families(sample: Sequence[Pair], given: dict[Pair, Label]) -> str:
    """Count the reasons given to more than one pair.

    One reason given over and over is a family of copies the sample met again and again,
    and says what the figure is made of.

    Args:
        sample: The pairs drawn.
        given: The verdict of each of them.

    Returns:
        One line per reason given to at least `TWICE` pairs, the commonest first: how
        many pairs, then the reason as it was recorded.
    """
    counted = Counter(given[pair].reason for pair in sample)
    return "\n".join(
        f"{count:>5}  {reason}" for reason, count in counted.most_common() if count >= TWICE
    )


def _parser() -> argparse.ArgumentParser:
    """Describe the command line: the pairs drawn and the verdicts given on them.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="precision",
        description="Measure precision on the labelled sample, with its Wilson interval.",
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=DEFAULT_SAMPLE,
        help="the pairs drawn, as a report of pairs (default %(default)s)",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help="the verdicts given on them, as JSON Lines (default %(default)s)",
    )
    return parser


def report(sample: Sequence[Pair], given: dict[Pair, Label]) -> str:
    """Write the whole of what the tool prints.

    Args:
        sample: The pairs drawn.
        given: The verdict of each of them.

    Returns:
        The table of the measures, then the count by criterion, then the reasons given to
        more than one pair, each under its heading.
    """
    return (
        f"{table(measures(sample, given))}\n"
        f"\n{BY_CRITERION}\n{criteria(sample, given)}\n"
        f"\n{RECURRING}\n{families(sample, given)}\n"
    )


def main(argv: Sequence[str], writer: TextIO) -> None:
    """Read the sample and its verdicts, and print the measures and the counts.

    Args:
        argv: The arguments, without the program name.
        writer: Where they are written.
    """
    options = _parser().parse_args(argv)
    sample = read_pairs(options.sample)
    given = verdicts(sample, read_labels(options.labels))
    # The whole report is built before a line of it is written: a sample whose verdicts
    # the counts refuse is not printed by halves, the table standing and the counts gone.
    writer.write(report(sample, given))


if __name__ == "__main__":
    main(sys.argv[1:], sys.stdout)
