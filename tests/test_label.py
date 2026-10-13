# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The format of the verdicts, how it is read, and the tool that records them."""

from __future__ import annotations

import io
import json
import runpy
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from benchmarks.label import (
    FORMAT_VERSION,
    Label,
    Session,
    copy_text,
    judge,
    main,
    read_labels,
    read_pairs,
    side_by_side,
)
from clonedigger.report import Span

# The script as `just label` runs it, to run it the same way in a test.
SCRIPT = Path(__file__).parent.parent / "benchmarks" / "label.py"
FIRST = Span("a.py", 1, 3)
SECOND = Span("b/c.py", 10, 12)
THIRD = Span("d.py", 5, 6)
# What the tool asks for each pair, word for word.
PROMPT = "y duplicated code, n not duplicated code, s skip for now, q stop here? "


def written(path: Path, *records: object) -> Path:
    """Write records as the lines of a file.

    Args:
        path: The file to write.
        *records: The records, each written as JSON on its own line.

    Returns:
        The file written.
    """
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def session(tmp_path: Path, answers: str, width: int = 20) -> tuple[Session, io.StringIO]:
    """Make a session that reads the answers given and writes to memory.

    Args:
        tmp_path: The directory the paths of the report are relative to.
        answers: What the reader answers, lines included.
        width: The columns each copy is given.

    Returns:
        The session, and what it writes.
    """
    shown = io.StringIO()
    return Session(tmp_path, width, io.StringIO(answers), shown), shown


def report_of(tmp_path: Path, *pairs: tuple[Span, Span], name: str = "pairs.json") -> Path:
    """Write a report of the pairs given, as `clonedigger --format json` writes it.

    Args:
        tmp_path: Where to write it.
        *pairs: The pairs it reports.
        name: The name of the report, for a test that needs more than one.

    Returns:
        The report.
    """
    return written(
        tmp_path / name,
        [
            {"first": asdict(first), "second": asdict(second), "distance": 1}
            for first, second in pairs
        ],
    )


def test_a_record_carries_the_version_and_the_two_copies(tmp_path: Path) -> None:
    """A label is written as one JSON object with the version, both copies and the verdict."""
    label = Label(FIRST, SECOND, clone=True, reason="same loop, other names")
    record = label.record()
    assert "\n" not in record
    assert json.loads(record) == {
        "version": FORMAT_VERSION,
        "first": {"path": "a.py", "start": 1, "end": 3},
        "second": {"path": "b/c.py", "start": 10, "end": 12},
        "clone": True,
        "reason": "same loop, other names",
    }
    assert read_labels(written(tmp_path / "labels.jsonl", json.loads(record))) == [label]


def test_a_reason_keeps_its_letters(tmp_path: Path) -> None:
    """A reason written with accents is recorded as it was typed, not escaped."""
    label = Label(FIRST, SECOND, clone=False, reason="décalé")
    assert "décalé" in label.record()
    assert read_labels(written(tmp_path / "labels.jsonl", json.loads(label.record()))) == [label]


def test_the_pair_names_the_record() -> None:
    """A label is known by its two copies, in order."""
    assert Label(FIRST, SECOND, clone=True, reason="").pair == (FIRST, SECOND)


def test_no_file_yet_means_no_verdict(tmp_path: Path) -> None:
    """Reading verdicts before any was given gives none, and no error."""
    assert read_labels(tmp_path / "labels.jsonl") == []


def test_the_verdicts_are_read_in_the_order_of_the_file(tmp_path: Path) -> None:
    """Every record of the file is read, in its order, and blank lines are left out."""
    labels = [
        Label(FIRST, SECOND, clone=True, reason="first"),
        Label(SECOND, FIRST, clone=False, reason="second"),
    ]
    path = tmp_path / "labels.jsonl"
    path.write_text("\n".join([labels[0].record(), "", labels[1].record(), "  "]), "utf-8")
    assert read_labels(path) == labels


def test_another_version_is_refused(tmp_path: Path) -> None:
    """A record of an unknown version is refused, naming the file, the line and the version."""
    record = json.loads(Label(FIRST, SECOND, clone=True, reason="x").record())
    path = written(tmp_path / "labels.jsonl", record, {**record, "version": 2})
    message = rf"labels\.jsonl:2: version 2 is not the version read, {FORMAT_VERSION}$"
    with pytest.raises(ValueError, match=message):
        read_labels(path)


def test_a_line_that_is_not_json_is_refused(tmp_path: Path) -> None:
    """A line that is not JSON at all is refused, naming the file and the line."""
    path = tmp_path / "labels.jsonl"
    path.write_text("{\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"labels\.jsonl:1: not JSON: "):
        read_labels(path)


BOTH_COPIES = {
    "version": FORMAT_VERSION,
    "first": {"path": "a.py", "start": 1, "end": 3},
    "second": {"path": "b/c.py", "start": 10, "end": 12},
}


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ([1], "a record must be a JSON object"),
        ({"version": "1"}, "version must be a whole number"),
        ({"version": True}, "version must be a whole number"),
        ({"version": FORMAT_VERSION}, "first must hold path, start and end"),
        ({**BOTH_COPIES, "first": 3}, "first must hold path, start and end"),
        ({**BOTH_COPIES, "first": {}}, "first: path must be a string"),
        (
            {**BOTH_COPIES, "first": {"path": "a.py", "start": "1"}},
            "first: start must be a whole number",
        ),
        (
            {**BOTH_COPIES, "first": {"path": "a.py", "start": 1}},
            "first: end must be a whole number",
        ),
        ({**BOTH_COPIES, "second": None}, "second must hold path, start and end"),
        ({**BOTH_COPIES, "second": {"path": "b/c.py"}}, "second: start must be a whole number"),
        (BOTH_COPIES, "clone must be true or false"),
        ({**BOTH_COPIES, "clone": "yes"}, "clone must be true or false"),
        ({**BOTH_COPIES, "clone": True}, "reason must be a string"),
    ],
)
def test_a_record_that_is_not_of_the_format_is_refused(
    tmp_path: Path, record: object, message: str
) -> None:
    """A record whose fields are not those of the format is refused, saying which and where."""
    with pytest.raises(TypeError, match=rf"labels\.jsonl:1: {message}$"):
        read_labels(written(tmp_path / "labels.jsonl", record))


def test_the_pairs_of_a_report_are_read_in_its_order(tmp_path: Path) -> None:
    """Reading a JSON report gives the two copies of each pair, in the order reported."""
    report = report_of(tmp_path, (FIRST, SECOND), (SECOND, FIRST))
    assert read_pairs(report) == [(FIRST, SECOND), (SECOND, FIRST)]


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        ({"first": 1}, "a report must be a JSON array of pairs"),
        ([2], "pair 1: a pair must be a JSON object"),
        ([{"second": asdict(SECOND)}], "pair 1: first must hold path, start and end"),
        ([{"first": asdict(FIRST)}], "pair 1: second must hold path, start and end"),
    ],
)
def test_a_report_that_is_not_pairs_is_refused(
    tmp_path: Path, broken: object, message: str
) -> None:
    """A report that is not an array of pairs is refused, naming the report and the pair."""
    with pytest.raises(TypeError, match=rf"pairs\.json: {message}$"):
        read_pairs(written(tmp_path / "pairs.json", broken))


def test_a_copy_is_read_with_its_line_numbers(tmp_path: Path) -> None:
    """The lines of a copy are read from its first to its last, each with its number."""
    (tmp_path / "a.py").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    assert copy_text(tmp_path, Span("a.py", 2, 3)) == ["    2 two", "    3 three"]


def test_a_copy_that_cannot_be_read_says_so(tmp_path: Path) -> None:
    """A copy whose file is gone is shown as a note, so that the run goes on."""
    shown = copy_text(tmp_path, Span("gone.py", 1, 2))
    assert len(shown) == 1
    assert shown[0].startswith("<cannot read gone.py: ")


def test_two_copies_are_shown_in_two_columns() -> None:
    """Side by side, each line is cut to the width, and the shorter block ends in blanks."""
    assert side_by_side(["ab", "x" * 6], ["cd"], 4) == "ab   | cd\nxxxx |"


def test_a_tab_is_shown_as_four_columns() -> None:
    """A line indented with tabs lines up with one indented with four blanks."""
    assert side_by_side(["\tx"], ["y"], 8) == "    x    | y"


def test_the_whole_exchange_is_what_the_reader_sees(tmp_path: Path) -> None:
    """A pair is shown with its place in the sample, both copies in columns, then the questions."""
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "c.py").write_text("\n" * 9 + "ten\neleven\n", encoding="utf-8")
    talk, shown = session(tmp_path, "y\nsame loop\n", width=12)
    assert list(judge([(FIRST, SECOND)], [], talk)) == [
        Label(FIRST, SECOND, clone=True, reason="same loop")
    ]
    assert shown.getvalue() == (
        "\n[1/1] a.py:1-3  ~  b/c.py:10-12\n"
        "    1 one    |    10 ten\n"
        "    2 two    |    11 eleven\n"
        "    3 three  |\n"
        f"{PROMPT}reason: "
    )


def test_a_verdict_is_recorded_with_its_reason(tmp_path: Path) -> None:
    """Answering y or n gives a label with that verdict and the reason typed."""
    talk, _ = session(tmp_path, "y\nsame loop\nN\nonly the shape\n")
    assert list(judge([(FIRST, SECOND), (SECOND, FIRST)], [], talk)) == [
        Label(FIRST, SECOND, clone=True, reason="same loop"),
        Label(SECOND, FIRST, clone=False, reason="only the shape"),
    ]


def test_a_skipped_pair_gives_no_verdict(tmp_path: Path) -> None:
    """Answering s leaves the pair unjudged and moves on to the next."""
    talk, _ = session(tmp_path, "s\ny\nlater\n")
    assert list(judge([(FIRST, SECOND), (SECOND, FIRST)], [], talk)) == [
        Label(SECOND, FIRST, clone=True, reason="later")
    ]


def test_an_answer_that_is_not_a_command_is_asked_again(tmp_path: Path) -> None:
    """Anything but a command leaves the pair unjudged and asks the same question again."""
    talk, shown = session(tmp_path, "maybe\ny\nsame loop\n")
    assert list(judge([(FIRST, SECOND)], [], talk)) == [
        Label(FIRST, SECOND, clone=True, reason="same loop")
    ]
    assert shown.getvalue().count(PROMPT) == 2


def test_stopping_leaves_the_rest_for_later(tmp_path: Path) -> None:
    """Answering q ends the run, and the pairs after it are not shown."""
    talk, shown = session(tmp_path, "q\n")
    assert not list(judge([(FIRST, SECOND), (SECOND, FIRST)], [], talk))
    assert shown.getvalue().count("[1/2]") == 1
    assert "[2/2]" not in shown.getvalue()
    assert shown.getvalue().endswith(PROMPT)


def test_the_end_of_the_input_stops_the_run(tmp_path: Path) -> None:
    """Nothing left to read stops the run, as q does, and ends the line it was asking on."""
    talk, shown = session(tmp_path, "")
    assert not list(judge([(FIRST, SECOND)], [], talk))
    assert shown.getvalue().endswith(f"{PROMPT}\n")


def test_a_pair_already_judged_is_not_asked_again(tmp_path: Path) -> None:
    """A pair whose verdict is recorded is left out, and the count follows what is left."""
    talk, shown = session(tmp_path, "y\nsame loop\n")
    judged = [Label(FIRST, SECOND, clone=False, reason="shifted")]
    assert list(judge([(FIRST, SECOND), (SECOND, FIRST)], judged, talk)) == [
        Label(SECOND, FIRST, clone=True, reason="same loop")
    ]
    assert "[1/1] b/c.py:10-12" in shown.getvalue()


def test_a_pair_with_no_reason_is_recorded_without_one(tmp_path: Path) -> None:
    """A reason left blank is recorded as blank, and the record still reads back."""
    talk, _ = session(tmp_path, "y\n\n")
    assert list(judge([(FIRST, SECOND)], [], talk)) == [Label(FIRST, SECOND, clone=True, reason="")]


def test_the_verdicts_are_added_to_the_file_as_they_are_given(tmp_path: Path) -> None:
    """A run adds one record per verdict to the file it was given, keeping the earlier ones."""
    labels = tmp_path / "labels.jsonl"
    labels.write_text(Label(FIRST, SECOND, clone=False, reason="shifted").record() + "\n", "utf-8")
    shown = io.StringIO()
    report = report_of(tmp_path, (FIRST, SECOND), (SECOND, FIRST), (FIRST, THIRD))
    main(
        ["--report", str(report), "--labels", str(labels), "--root", str(tmp_path)],
        io.StringIO("y\nsame loop\nn\nshifted window\n"),
        shown,
    )
    assert read_labels(labels) == [
        Label(FIRST, SECOND, clone=False, reason="shifted"),
        Label(SECOND, FIRST, clone=True, reason="same loop"),
        Label(FIRST, THIRD, clone=False, reason="shifted window"),
    ]
    assert shown.getvalue().endswith(f"3 of 3 pairs judged, in {labels}\n")


def test_one_file_for_several_reports_counts_the_pairs_of_the_report_read(tmp_path: Path) -> None:
    """A file holding the verdicts of other reports does not count towards the one read."""
    labels = tmp_path / "labels.jsonl"
    where = ["--labels", str(labels), "--root", str(tmp_path)]
    first = str(report_of(tmp_path, (FIRST, SECOND), name="first.json"))
    second = str(report_of(tmp_path, (FIRST, THIRD), name="second.json"))
    shown = io.StringIO()
    main(["--report", first, *where], io.StringIO("y\nsame loop\n"), shown)
    main(["--report", second, *where], io.StringIO("n\nshifted window\n"), shown)
    assert shown.getvalue().count(f"1 of 1 pairs judged, in {labels}\n") == 2
    assert read_labels(labels) == [
        Label(FIRST, SECOND, clone=True, reason="same loop"),
        Label(FIRST, THIRD, clone=False, reason="shifted window"),
    ]


def test_the_copies_are_read_from_the_current_directory_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --root, the paths of the report are read from the directory the tool runs in."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "d.py").write_text("\n" * 4 + "five\nsix\n", encoding="utf-8")
    shown = io.StringIO()
    report = report_of(tmp_path, (FIRST, THIRD))
    options = ["--report", str(report), "--labels", str(tmp_path / "labels.jsonl")]
    main(options, io.StringIO(), shown)
    assert "    1 one" in shown.getvalue()
    assert "    5 five" in shown.getvalue()


def test_the_width_given_is_the_width_of_each_column(tmp_path: Path) -> None:
    """--width says how many columns each copy is given."""
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "d.py").write_text("\n" * 4 + "five\nsix\n", encoding="utf-8")
    shown = io.StringIO()
    report = report_of(tmp_path, (FIRST, THIRD))
    main(
        [
            "--report",
            str(report),
            "--labels",
            str(tmp_path / "labels.jsonl"),
            "--root",
            str(tmp_path),
            "--width",
            "12",
        ],
        io.StringIO(),
        shown,
    )
    assert "    1 one    |     5 five" in shown.getvalue()


def test_the_report_to_judge_must_be_named(capsys: pytest.CaptureFixture[str]) -> None:
    """Without --report there is nothing to judge: the command refuses and says so."""
    with pytest.raises(SystemExit) as exit_info:
        main([], io.StringIO(), io.StringIO())
    assert exit_info.value.code == 2
    assert "--report" in capsys.readouterr().err


def test_help_is_what_the_user_reads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--help prints the options, their meaning and their defaults, as recorded.

    Regenerate tests/data/label-help.txt with
    `COLUMNS=100 uv run python benchmarks/label.py --help` after a deliberate change.
    """
    monkeypatch.setenv("COLUMNS", "100")
    with pytest.raises(SystemExit):
        main(["--help"], io.StringIO(), io.StringIO())
    expected = (Path(__file__).parent / "data" / "label-help.txt").read_text(encoding="utf-8")
    assert capsys.readouterr().out == expected


def test_running_the_script_judges_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run as a script, the tool reads the report named on the command line."""
    labels = tmp_path / "labels.jsonl"
    monkeypatch.setattr(
        sys,
        "argv",
        ["label", "--report", str(report_of(tmp_path)), "--labels", str(labels)],
    )
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert capsys.readouterr().out == f"0 of 0 pairs judged, in {labels}\n"
