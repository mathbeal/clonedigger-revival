# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The draw of the sample, the Wilson interval, and the table precision is read from."""

from __future__ import annotations

import io
import json
import math
import runpy
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from benchmarks.label import Label
from benchmarks.precision import (
    CONFIDENCE,
    Measure,
    down,
    draw,
    main,
    measures,
    overlapping,
    project,
    table,
    up,
    verdicts,
    wilson,
)
from clonedigger.report import Span

# The script as `just precision` runs it, to run it the same way in a test.
SCRIPT = Path(__file__).parent.parent / "benchmarks" / "precision.py"
# Two copies in one release, two in another, so that the table has a row per release.
FIRST = Span("one-1.0/a.py", 1, 5)
SECOND = Span("one-1.0/b.py", 10, 14)
THIRD = Span("two-2.0/c.py", 1, 5)
FOURTH = Span("two-2.0/c.py", 4, 8)
# The multiple of the standard error a 95 % interval reaches, 1.96 to two decimals.
SPREAD = statistics.NormalDist().inv_cdf((1 + CONFIDENCE) / 2)


def population(count: int) -> list[tuple[Span, Span]]:
    """Make as many pairs as asked, each in its own place.

    Args:
        count: How many pairs.

    Returns:
        The pairs, one per file, in the order of their names.
    """
    return [(Span(f"p-1.0/f{number}.py", 1, 5), SECOND) for number in range(count)]


def sample_of(tmp_path: Path, *pairs: tuple[Span, Span]) -> Path:
    """Write a sample of the pairs given, in the format of a report.

    Args:
        tmp_path: Where to write it.
        *pairs: The pairs drawn.

    Returns:
        The file written.
    """
    path = tmp_path / "sample.json"
    records = [{"first": asdict(first), "second": asdict(second)} for first, second in pairs]
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def labels_of(tmp_path: Path, *labels: Label) -> Path:
    """Write the verdicts given, as JSON Lines.

    Args:
        tmp_path: Where to write them.
        *labels: The verdicts.

    Returns:
        The file written.
    """
    path = tmp_path / "labels.jsonl"
    path.write_text("".join(label.record() + "\n" for label in labels), encoding="utf-8")
    return path


def test_the_same_sample_is_drawn_at_every_run() -> None:
    """A seed and a size draw the same pairs, in the same order, every time."""
    drawn = draw(population(10), 3, 1)
    assert drawn == draw(population(10), 3, 1)
    assert [first.path for first, _ in drawn] == ["p-1.0/f2.py", "p-1.0/f1.py", "p-1.0/f4.py"]


def test_another_seed_draws_another_sample() -> None:
    """The seed chooses the sample: another seed gives another one."""
    assert draw(population(10), 3, 1) != draw(population(10), 3, 2)


def test_the_draw_does_not_depend_on_the_order_reported() -> None:
    """The same pairs listed in another order give the same sample."""
    pairs = population(10)
    assert draw(pairs, 4, 1) == draw(list(reversed(pairs)), 4, 1)


def test_the_whole_report_can_be_drawn() -> None:
    """A sample as large as the report holds every pair of it, once."""
    pairs = population(6)
    drawn = draw(pairs, 6, 1)
    assert len(drawn) == len(pairs)
    assert set(drawn) == set(pairs)


def test_a_sample_larger_than_the_report_is_refused() -> None:
    """Asking for more pairs than were reported is refused, with both counts."""
    with pytest.raises(ValueError, match=r"^3 pairs reported, 4 asked for$"):
        draw(population(3), 4, 1)


def test_the_interval_of_a_known_sample() -> None:
    """Half of ten pairs gives the Wilson 95 % interval of the textbooks, 23.7 % to 76.4 %."""
    low, high = wilson(5, 10)
    assert (low, high) == pytest.approx((0.2365931, 0.7634069))
    assert f"[{down(low)}, {up(high)}]" == "[23.6 %, 76.4 %]"


def test_a_sample_with_one_pair_has_an_interval() -> None:
    """One pair, judged duplicated code, bounds precision between 20.6 % and 100 %."""
    assert wilson(1, 1) == pytest.approx((0.2065493, 1.0))


@pytest.mark.parametrize("pairs", [1, 8, 33, 60])
def test_a_sample_with_no_clone_is_bounded_from_nothing(pairs: int) -> None:
    """No pair of the sample duplicated code bounds precision from 0, not from below it."""
    assert wilson(0, pairs)[0] == 0.0  # ruff: ignore[float-equality-comparison]


@pytest.mark.parametrize("pairs", [1, 8, 33, 60])
def test_a_sample_of_nothing_but_clones_is_bounded_by_everything(pairs: int) -> None:
    """Every pair duplicated code bounds precision up to 1, never a step above it."""
    assert wilson(pairs, pairs)[1] == 1.0  # ruff: ignore[float-equality-comparison]


def test_a_wider_confidence_gives_a_wider_interval() -> None:
    """Asked for 99 % instead of 95 %, the interval reaches further on both sides."""
    low, high = wilson(5, 10)
    wider_low, wider_high = wilson(5, 10, confidence=0.99)
    assert wider_low < low
    assert wider_high > high


def test_an_empty_sample_is_refused() -> None:
    """A sample with no pair at all says nothing about precision, and is refused."""
    with pytest.raises(ValueError, match=r"^an empty sample says nothing about precision$"):
        wilson(0, 0)


@pytest.mark.parametrize("clones", [-1, 4])
def test_more_clones_than_pairs_is_refused(clones: int) -> None:
    """A count of clones outside 0 to the size of the sample is refused, with both counts."""
    with pytest.raises(ValueError, match=rf"^{clones} of 3 pairs cannot be duplicated code$"):
        wilson(clones, 3)


@given(pairs=st.integers(min_value=2, max_value=2000), part=st.floats(0, 1))
def test_the_bounds_are_the_shares_whose_error_reaches_the_sample(pairs: int, part: float) -> None:
    """Each bound is a share whose own standard error, times 1.96, reaches the share measured.

    Away from the two ends, where a share of 0 or of 1 has no error to speak of and the
    arithmetic is all cancellation: those two are pinned by their own tests.
    """
    clones = 1 + round(part * (pairs - 2))
    measured = clones / pairs
    for bound in wilson(clones, pairs):
        error = math.sqrt(bound * (1 - bound) / pairs)
        assert abs(measured - bound) == pytest.approx(SPREAD * error, rel=1e-9)


@pytest.mark.parametrize(
    ("share", "rounded_down", "rounded_up"),
    [(49 / 60, "81.6 %", "81.7 %"), (0.5, "50.0 %", "50.0 %"), (1.0, "100.0 %", "100.0 %")],
)
def test_a_share_is_rounded_away_from_the_advantage(
    share: float, rounded_down: str, rounded_up: str
) -> None:
    """A share is written to one decimal, down for precision and the floor, up for the ceiling."""
    assert down(share) == rounded_down
    assert up(share) == rounded_up


def test_a_pair_is_named_by_the_release_it_was_found_in() -> None:
    """The release of a pair is the first part of the path of its first copy."""
    assert project((FIRST, SECOND)) == "one-1.0"
    assert project((Span("a.py", 1, 5), SECOND)) == "a.py"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (Span("a.py", 1, 5), Span("a.py", 4, 8)),
        (Span("a.py", 1, 5), Span("a.py", 5, 9)),
        (Span("a.py", 5, 9), Span("a.py", 1, 5)),
        (Span("a.py", 4, 8), Span("a.py", 1, 5)),
    ],
)
def test_two_copies_of_one_file_that_share_lines_overlap(first: Span, second: Span) -> None:
    """Two copies of one file whose lines meet overlap, down to one line, in either order."""
    assert overlapping((first, second)) is True


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (Span("a.py", 1, 5), Span("a.py", 6, 10)),
        (Span("a.py", 6, 10), Span("a.py", 1, 5)),
        (Span("a.py", 1, 5), Span("b.py", 1, 5)),
    ],
)
def test_two_copies_that_share_no_line_do_not_overlap(first: Span, second: Span) -> None:
    """Two copies in other files, or in one file but apart, do not overlap."""
    assert overlapping((first, second)) is False


def test_the_verdict_of_each_pair_drawn_is_read() -> None:
    """Every pair of the sample gets the verdict recorded for it."""
    judged = [
        Label(FIRST, SECOND, clone=True, reason="same loop"),
        Label(THIRD, FOURTH, clone=False, reason="only the shape"),
    ]
    assert verdicts([(FIRST, SECOND), (THIRD, FOURTH)], judged) == {
        (FIRST, SECOND): True,
        (THIRD, FOURTH): False,
    }


def test_a_verdict_on_another_report_is_left_out() -> None:
    """A verdict on a pair the sample does not hold is ignored, not counted."""
    judged = [
        Label(SECOND, FIRST, clone=False, reason="another report"),
        Label(FIRST, SECOND, clone=True, reason="same loop"),
    ]
    assert verdicts([(FIRST, SECOND)], judged) == {(FIRST, SECOND): True}


def test_a_pair_judged_twice_is_refused() -> None:
    """Two verdicts on one pair of the sample are refused, naming the pair."""
    judged = [
        Label(FIRST, SECOND, clone=True, reason="same loop"),
        Label(FIRST, SECOND, clone=False, reason="second thoughts"),
    ]
    with pytest.raises(ValueError, match=r"^one-1.0/a.py:1-5 ~ one-1.0/b.py:10-14: judged twice$"):
        verdicts([(FIRST, SECOND)], judged)


def test_a_pair_not_judged_yet_is_refused() -> None:
    """A sample not judged to its end is refused, with how many are left and the first of them."""
    judged = [Label(THIRD, FOURTH, clone=True, reason="same loop")]
    message = r"^2 pairs of the sample not judged yet, the first one-1.0/a.py:1-5 ~ "
    with pytest.raises(ValueError, match=message):
        verdicts([(FIRST, SECOND), (SECOND, FIRST), (THIRD, FOURTH)], judged)


def test_the_precision_of_a_measure() -> None:
    """The precision of a set of pairs is the share of them that are duplicated code."""
    assert Measure("the whole sample", 60, 49).precision == pytest.approx(49 / 60)


def test_each_release_is_measured_apart_and_the_whole_sample_too() -> None:
    """The sample gives one measure per release, in order, then one over all of it."""
    sample = [(FIRST, SECOND), (SECOND, FIRST), (THIRD, FOURTH)]
    judged = {(FIRST, SECOND): True, (SECOND, FIRST): False, (THIRD, FOURTH): True}
    assert measures(sample, judged)[:3] == [
        Measure("one-1.0", 2, 1),
        Measure("two-2.0", 1, 1),
        Measure("the whole sample", 3, 2),
    ]


def test_the_pairs_whose_copies_overlap_are_measured_apart() -> None:
    """A sample holding overlapping pairs is measured with them, and again without them."""
    sample = [(FIRST, SECOND), (THIRD, FOURTH)]
    judged = {(FIRST, SECOND): True, (THIRD, FOURTH): False}
    assert measures(sample, judged)[-2:] == [
        Measure("their copies overlap", 1, 0),
        Measure("the sample without them", 1, 1),
    ]


def test_a_sample_with_no_overlapping_pair_is_not_split() -> None:
    """With no overlapping pair, the split would repeat the whole sample: it is left out."""
    sample = [(FIRST, SECOND)]
    assert measures(sample, {(FIRST, SECOND): True}) == [
        Measure("one-1.0", 1, 1),
        Measure("the whole sample", 1, 1),
    ]


def test_the_table_is_what_a_reader_reads() -> None:
    """The table has a heading and one row per measure: counts, precision and interval."""
    assert table([Measure("the whole sample", 60, 49)]) == (
        "                                  pairs duplicated code  precision  95 % Wilson\n"
        "the whole sample                     60              49     81.6 %  [70.0 %, 89.5 %]"
    )


def test_the_figure_the_readme_gives_is_the_figure_of_the_sample_committed() -> None:
    """The sample committed is judged to its end and gives the precision the README gives."""
    root = Path(__file__).parent.parent
    shown = io.StringIO()
    main(
        [
            "--sample",
            str(root / "benchmarks" / "sample.json"),
            "--labels",
            str(root / "benchmarks" / "labels.jsonl"),
        ],
        shown,
    )
    assert (
        "the whole sample                     60              56     93.3 %  [84.0 %, 97.4 %]"
        in shown.getvalue().splitlines()
    )


def test_the_table_is_printed_for_the_files_given(tmp_path: Path) -> None:
    """The tool reads the sample and the verdicts it is given, and prints their table."""
    sample = sample_of(tmp_path, (FIRST, SECOND), (THIRD, FOURTH))
    judged = labels_of(
        tmp_path,
        Label(FIRST, SECOND, clone=True, reason="same loop"),
        Label(THIRD, FOURTH, clone=True, reason="shifted window"),
    )
    shown = io.StringIO()
    main(["--sample", str(sample), "--labels", str(judged)], shown)
    assert shown.getvalue().splitlines()[1:] == [
        "one-1.0                               1               1    100.0 %  [20.6 %, 100.0 %]",
        "two-2.0                               1               1    100.0 %  [20.6 %, 100.0 %]",
        "the whole sample                      2               2    100.0 %  [34.2 %, 100.0 %]",
        "their copies overlap                  1               1    100.0 %  [20.6 %, 100.0 %]",
        "the sample without them               1               1    100.0 %  [20.6 %, 100.0 %]",
    ]


def test_help_is_what_the_user_reads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--help prints the options, their meaning and their defaults, as recorded.

    Regenerate tests/data/precision-help.txt with
    `COLUMNS=100 uv run python -m benchmarks.precision --help` after a deliberate change.
    """
    monkeypatch.setenv("COLUMNS", "100")
    with pytest.raises(SystemExit):
        main(["--help"], io.StringIO())
    expected = (Path(__file__).parent / "data" / "precision-help.txt").read_text(encoding="utf-8")
    assert capsys.readouterr().out == expected


def test_running_the_script_measures_the_sample_committed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run as a script with no argument, the tool measures the files committed."""
    monkeypatch.chdir(Path(__file__).parent.parent)
    monkeypatch.setattr(sys, "argv", ["precision"])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert "the whole sample" in capsys.readouterr().out
