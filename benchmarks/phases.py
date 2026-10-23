# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the time of a run goes: step by step, and bucket by bucket.

`just bench` times a whole run. This script splits that time between the steps of the
pipeline, and says which bucket of statements of the same rough shape costs the most:
gathering a bucket into clusters and marking its statements weighs every statement
against every cluster, so a bucket of many clusters costs more than a bigger bucket of
few, whatever its number of statements.

The steps are timed one by one, then the whole run is timed again by `find_clones`: what
it takes beyond the steps measured is the suffix tree and the refinement. The pipeline is
therefore run twice, and the figures of the two runs are read together, which is why the
script takes about twice as long as `just bench` on the same paths, and why that last
figure means something only on paths the run takes seconds on: below that, the two runs
differ by more than the figure itself.

Run it with `just phases`, on the standard library by default.
"""

from __future__ import annotations

import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from clonedigger.cli import python_files
from clonedigger.detection import (
    Settings,
    buckets_by_shape,
    build_clusters,
    find_clones,
    long_sequences,
    mark_statements,
)
from clonedigger.python_frontend import read_source

if TYPE_CHECKING:
    from collections.abc import Sequence

    from clonedigger.python_frontend import SourceFile, Statement

# What `just bench` leaves out of the standard library: its own test suites, and the
# editor, whose own test suite lies inside it.
LEFT_OUT: Final = ("test", "tests", "idlelib")


@dataclass(frozen=True)
class Bucket:
    """One bucket of statements of the same rough shape, and what it cost.

    Attributes:
        statements: How many statements it holds.
        clusters: How many clusters they were gathered into.
        gathering: How long gathering them into clusters took, in seconds.
        marking: How long marking them took, in seconds.
    """

    statements: int
    clusters: int
    gathering: float
    marking: float

    @property
    def seconds(self) -> float:
        """How long the bucket took in all."""
        return self.gathering + self.marking


def read(paths: Sequence[Path]) -> list[SourceFile]:
    """Parse every Python file under the given paths.

    Args:
        paths: The files and directories to read.

    Returns:
        The files that were read; one that cannot be is named on the error stream and
        left out, as the command does.
    """
    files: list[SourceFile] = []
    for path in python_files(paths, LEFT_OUT):
        try:
            files.append(read_source(path, path.read_text(encoding="utf-8"), ()))
        except (SyntaxError, OSError, UnicodeDecodeError) as error:
            sys.stderr.write(f"left out: {path}: {error}\n")
    return files


def gather_and_mark(buckets: Sequence[list[Statement]], settings: Settings) -> list[Bucket]:
    """Gather each bucket into clusters and mark its statements, timing both.

    Args:
        buckets: The statements of each bucket, as `buckets_by_shape` groups them.
        settings: The thresholds of the detection.

    Returns:
        What each bucket holds and what it cost.
    """
    measured: list[Bucket] = []
    for statements in buckets:
        start = time.perf_counter()
        clusters = build_clusters(statements, settings.clustering_threshold)
        gathered = time.perf_counter()
        mark_statements(statements, clusters)
        measured.append(
            Bucket(
                len(statements),
                len(clusters),
                gathered - start,
                time.perf_counter() - gathered,
            )
        )
    return measured


def _share(seconds: float, whole: float) -> str:
    """Write a duration and the share of a whole it makes.

    Args:
        seconds: The duration.
        whole: What it is a share of.

    Returns:
        The two, as `12.3 s (45 %)`.
    """
    return f"{seconds:6.1f} s ({100 * seconds / whole:3.0f} %)"


def _report(buckets: Sequence[Bucket], steps: Sequence[tuple[str, float]], whole: float) -> str:
    """Write down the share of each step, then the biggest and the costliest bucket.

    Args:
        buckets: What each bucket held and cost.
        steps: Each step and how long it took, in the order they run.
        whole: How long the run took in all.

    Returns:
        The report, one step to a line.
    """
    lines = [f"{name:24}{_share(seconds, whole)}" for name, seconds in steps]
    lines.append(f"{'whole run':24}{whole:6.1f} s")
    spent = sum(bucket.seconds for bucket in buckets)
    for name, bucket in (
        ("biggest bucket", max(buckets, key=lambda bucket: bucket.statements)),
        ("costliest bucket", max(buckets, key=lambda bucket: bucket.seconds)),
    ):
        lines.append(
            f"\n{name}: {bucket.statements:,} statements, {bucket.clusters:,} clusters, "
            f"{bucket.seconds:.1f} s, {100 * bucket.seconds / spent:.0f} % of the two steps"
        )
    return "\n".join(lines)


def main(names: Sequence[str]) -> None:
    """Measure the steps on the given paths, the standard library by default.

    Args:
        names: The files and directories to read.
    """
    paths = [Path(name) for name in names] or [Path(sysconfig.get_path("stdlib"))]
    settings = Settings()
    start = time.perf_counter()
    files = read(paths)
    reading = time.perf_counter() - start
    start = time.perf_counter()
    sequences = long_sequences(files, settings)
    buckets = buckets_by_shape(sequences, settings.hashing_depth)
    shaping = time.perf_counter() - start
    measured = gather_and_mark(list(buckets.values()), settings)
    start = time.perf_counter()
    clones = find_clones(files, settings)
    run = time.perf_counter() - start
    # The steps the second run goes through again: what it takes beyond them is the
    # suffix tree and the refinement.
    inside = [
        ("shaping into buckets", shaping),
        ("gathering into clusters", sum(bucket.gathering for bucket in measured)),
        ("marking the statements", sum(bucket.marking for bucket in measured)),
    ]
    steps = [
        ("reading the files", reading),
        *inside,
        ("suffix tree, refining", run - sum(seconds for _, seconds in inside)),
    ]
    sys.stdout.write(
        f"{len(files):,} files, {sum(map(len, sequences)):,} statements in "
        f"{len(sequences):,} sequences, {len(buckets):,} buckets, {len(clones):,} clones\n\n"
        f"{_report(measured, steps, reading + run)}\n"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
