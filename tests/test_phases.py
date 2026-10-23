# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The split of a run between its steps, and the two buckets the report names."""

from __future__ import annotations

import io
import math
import runpy
import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from benchmarks.phases import (
    LEFT_OUT,
    Bucket,
    gather_and_mark,
    main,
    read,
    report,
    share,
    steps_of,
)
from clonedigger.detection import Settings, buckets_by_shape, long_sequences

if TYPE_CHECKING:
    import pytest

# The script as `just phases` runs it, to run it the same way in a test.
SCRIPT = Path(__file__).parent.parent / "benchmarks" / "phases.py"

# A module holding one clone: the same loop twice, under other names, over the five
# lines a clone must span.
CLONED = dedent("""\
    def total(items):
        total = 0
        for item in items:
            price = item.price
            total = total + price
        return total


    def sum_up(lines):
        amount = 0
        for line in lines:
            cost = line.cost
            amount = amount + cost
        return amount
    """)


def package(root: Path) -> Path:
    """Write a package to read, with a directory of each name the script leaves out.

    Args:
        root: Where to write it.

    Returns:
        The directory to read.
    """
    directory = root / "pkg"
    directory.mkdir()
    for name in ("one.py", "two.py"):
        (directory / name).write_text(CLONED, encoding="utf-8")
    for name in LEFT_OUT:
        (directory / name).mkdir()
        (directory / name / "three.py").write_text(CLONED, encoding="utf-8")
    return directory


def test_a_directory_the_recipe_leaves_out_is_not_read(tmp_path: Path) -> None:
    """The directories `just bench` skips, its own test suites and the editor, are skipped."""
    assert sorted(file.path.name for file in read([package(tmp_path)])) == ["one.py", "two.py"]
    assert LEFT_OUT == ("test", "tests", "idlelib")


def test_a_file_that_will_not_parse_is_named_and_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file the running Python cannot read is named on the error stream, and left out."""
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "fine.py").write_text(CLONED, encoding="utf-8")
    assert [file.path.name for file in read([tmp_path])] == ["fine.py"]
    printed = capsys.readouterr().err
    assert printed.startswith(f"left out: {tmp_path / 'broken.py'}: ")
    assert printed.endswith("\n")


def test_each_bucket_reports_what_it_holds_and_what_it_cost(tmp_path: Path) -> None:
    """A bucket says how many statements and clusters it holds, and its two durations."""
    settings = Settings()
    buckets = buckets_by_shape(long_sequences(read([package(tmp_path)]), settings), 1)
    measured = gather_and_mark(list(buckets.values()), settings)
    assert [bucket.statements for bucket in measured] == [
        len(statements) for statements in buckets.values()
    ]
    assert all(1 <= bucket.clusters <= bucket.statements for bucket in measured)
    assert all(bucket.seconds == bucket.gathering + bucket.marking for bucket in measured)
    # A bucket this small takes a fraction of a second: either duration timed the wrong
    # way round would read as the clock itself.
    assert all(0 <= bucket.gathering < 1 and 0 <= bucket.marking < 1 for bucket in measured)


def test_the_last_step_is_what_the_run_took_beyond_the_three_it_repeats() -> None:
    """Four steps are timed, and the fifth is the run less the three inside it."""
    buckets = [Bucket(4, 2, 1.0, 2.0), Bucket(3, 1, 0.5, 0.5)]
    assert steps_of(4.0, 1.0, buckets, 10.0) == [
        ("reading the files", 4.0),
        ("shaping into buckets", 1.0),
        ("gathering into clusters", 1.5),
        ("marking the statements", 2.5),
        ("suffix tree, refining", 5.0),
    ]


def test_the_steps_add_up_to_the_whole_run() -> None:
    """Whatever the run, the five steps add up to the reading plus the run itself."""
    steps = steps_of(0.7, 0.3, [Bucket(4, 2, 1.25, 0.75), Bucket(2, 1, 0.5, 0.25)], 6.0)
    assert math.isclose(sum(seconds for _, seconds in steps), 0.7 + 6.0)


def test_a_duration_is_written_with_the_share_it_makes() -> None:
    """A step is written as its seconds, then its share of the whole as a percentage."""
    assert share(2.0, 10.0) == "   2.0 s ( 20 %)"


def test_the_report_names_each_step_then_the_two_buckets_that_matter() -> None:
    """The steps with their shares, the whole run, then the biggest and costliest bucket."""
    buckets = [Bucket(4668, 50, 0.25, 0.25), Bucket(1586, 1062, 1.0, 2.5)]
    steps = [("reading the files", 2.0), ("marking the statements", 8.0)]
    assert report(buckets, steps).splitlines() == [
        "reading the files          2.0 s ( 20 %)",
        "marking the statements     8.0 s ( 80 %)",
        "whole run                 10.0 s",
        "",
        "biggest bucket: 4,668 statements, 50 clusters, 0.5 s, 12.5 % of the two steps",
        "",
        "costliest bucket: 1,586 statements, 1,062 clusters, 3.5 s, 87.5 % of the two steps",
    ]


# This test comes before the next one on purpose: a run that read the whole standard
# library instead of the paths it was given fails here in a moment, where the test below
# would take the time of a whole run to notice it.
def test_with_no_path_given_the_standard_library_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given no path, the script reads the standard library of the running Python."""
    asked: list[str] = []

    def stub(name: str) -> str:
        """Answer the path of the package written for this test.

        Args:
            name: The path asked for.

        Returns:
            The directory to read.
        """
        asked.append(name)
        return str(package(tmp_path))

    monkeypatch.setattr("benchmarks.phases.sysconfig.get_path", stub)
    shown = io.StringIO()
    main([], shown)
    assert asked == ["stdlib"]
    assert shown.getvalue().startswith("2 files, ")


def test_the_report_counts_the_files_the_statements_the_buckets_and_the_clones(
    tmp_path: Path,
) -> None:
    """On the paths given, the report heads with what was read and what was found."""
    shown = io.StringIO()
    main([str(package(tmp_path))], shown)
    lines = shown.getvalue().splitlines()
    assert lines[0] == "2 files, 16 statements in 6 sequences, 4 buckets, 3 clones"
    assert [line[:24].rstrip() for line in lines[2:8]] == [
        "reading the files",
        "shaping into buckets",
        "gathering into clusters",
        "marking the statements",
        "suffix tree, refining",
        "whole run",
    ]
    # A target this small takes a fraction of a second: a step timed the wrong way round
    # would read as the clock itself. The last step is the run less the three inside it,
    # which the second pass runs faster, so it can come out just below zero.
    assert all(abs(float(line[24:].split(" s ")[0])) < 1 for line in lines[2:7])
    assert float(lines[7][24:].removesuffix(" s")) < 1
    assert lines[9].startswith("biggest bucket: 4 statements, ")


def test_running_the_script_measures_the_paths_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run as a script, the tool writes its report for the paths on the command line."""
    monkeypatch.setattr(sys, "argv", ["phases", str(package(tmp_path))])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert capsys.readouterr().out.startswith("2 files, ")
