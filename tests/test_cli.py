# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The command reads files and directories, and reports in text or JSON."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from clonedigger.cli import main, python_files
from clonedigger.detection import Clone, Settings

INPUTS = Path(__file__).parent / "golden" / "inputs"


def test_text_report(capsys: pytest.CaptureFixture[str]) -> None:
    """The clone of the recorded inputs is printed, and the status says clones exist."""
    assert main([str(INPUTS)]) == 1
    out = capsys.readouterr().out
    assert "prices.py:13-18  ~  " in out
    assert out.rstrip().endswith("1 clone found.")


def test_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    """JSON lists each clone's two spans and its distance."""
    main([str(INPUTS), "--format", "json"])
    (finding,) = json.loads(capsys.readouterr().out)
    assert finding["first"]["start"] == 13
    assert finding["first"]["end"] == 18
    assert finding["distance"] == 4


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--size-threshold", "30"),
        ("--distance-threshold", "1"),
        ("--clustering-threshold", "0"),
    ],
)
def test_each_threshold_reaches_the_detection(option: str, value: str) -> None:
    """Each threshold, set on its own, changes what is found on the recorded inputs."""
    assert main([str(INPUTS)]) == 1
    assert main([str(INPUTS), option, value]) == 0


def test_force_reaches_the_detection(tmp_path: Path) -> None:
    """--force keeps the long runs of similar statements that are otherwise left out."""
    lines = "".join(f"value_{index} = compute({index})\n" for index in range(15))
    for name in ("a", "b"):
        (tmp_path / f"{name}.py").write_text(lines)
    assert main([str(tmp_path)]) == 0
    assert main([str(tmp_path), "--force"]) == 1


def test_the_default_format_is_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Without --format, the report is the text one."""
    main([str(INPUTS)])
    assert capsys.readouterr().out.endswith("1 clone found.\n")


def test_prefixes_are_a_comma_separated_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Several prefixes, with spaces around the commas, each leave functions out."""
    assert main([str(INPUTS), "--func-prefixes", "nothing_, total_with_rebate"]) == 0
    assert main([str(INPUTS), "--func-prefixes", "nothing_,total_with_rebate"]) == 0
    assert main([str(INPUTS), "--func-prefixes", " , "]) == 1
    # A prefix is a whole word, not a set of letters: "x_total" skips nothing here.
    assert main([str(INPUTS), "--func-prefixes", "x_total"]) == 1
    capsys.readouterr()


def test_ignored_directories_are_passed_on(tmp_path: Path) -> None:
    """--ignore-dir keeps a copy out of the comparison."""
    source = (INPUTS / "prices.py").read_text()
    copy = source.replace("def total_with_rebate", "def unused_total")
    (tmp_path / "a.py").write_text(source.split("def total_with_rebate")[0])
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "b.py").write_text(copy.split("def unused_total")[0])
    assert main([str(tmp_path)]) == 1
    assert main([str(tmp_path), "--ignore-dir", "vendor"]) == 0


def test_files_are_read_as_utf8(tmp_path: Path) -> None:
    """A file with accented characters is read, whatever the locale."""
    (tmp_path / "a.py").write_text("libellé = 'été'\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0


def test_an_unreadable_file_wins_over_clones(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With clones found and a file unreadable, the status is 2."""
    (tmp_path / "broken.py").write_text("def (:\n")
    assert main([str(INPUTS), str(tmp_path / "broken.py")]) == 2
    capsys.readouterr()


def test_thresholds_are_passed_on(capsys: pytest.CaptureFixture[str]) -> None:
    """Every threshold option reaches the detection."""
    status = main(
        [
            str(INPUTS),
            "--size-threshold",
            "30",
            "--distance-threshold",
            "5",
            "--clustering-threshold",
            "10",
            "--hashing-depth",
            "1",
            "--force",
            "--func-prefixes",
            "total_",
        ]
    )
    assert status == 0
    assert capsys.readouterr().out.strip() == "0 clones found."


def test_prefixes_leave_functions_out(capsys: pytest.CaptureFixture[str]) -> None:
    """Leaving out one of the two copies leaves no clone."""
    assert main([str(INPUTS / "prices.py"), "--func-prefixes", "total_with_rebate"]) == 0
    assert "0 clones found." in capsys.readouterr().out


def test_unreadable_files_are_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A file that does not parse is named on stderr, and the status is 2."""
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n")
    assert main([str(broken)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_directories_are_walked_and_names_skipped(tmp_path: Path) -> None:
    """Python files are found below a directory, except under ignored names."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "venv").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("")
    (tmp_path / "a.py").write_text("")
    (tmp_path / "venv" / "c.py").write_text("")
    (tmp_path / "notes.txt").write_text("")
    (tmp_path / "pkg" / "venv").mkdir()
    (tmp_path / "pkg" / "venv" / "d.py").write_text("")
    found = [path.relative_to(tmp_path).as_posix() for path in python_files([tmp_path], ["venv"])]
    assert found == ["a.py", "pkg/b.py"]
    assert len(list(python_files([tmp_path], []))) == 4


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python -m clonedigger runs the command and exits with its status."""
    monkeypatch.setattr(sys, "argv", ["clonedigger", str(INPUTS)])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("clonedigger", run_name="__main__")
    assert exit_info.value.code == 1


def test_help_is_what_the_user_reads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--help prints the options, their meaning and their defaults, as recorded.

    Regenerate tests/data/help.txt with `COLUMNS=100 clonedigger --help` after a
    deliberate change.
    """
    monkeypatch.setenv("COLUMNS", "100")
    with pytest.raises(SystemExit):
        main(["--help"])
    expected = (Path(__file__).parent / "data" / "help.txt").read_text()
    assert capsys.readouterr().out == expected


def test_every_option_reaches_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The values given on the command line are the settings the detection receives."""
    received: list[Settings] = []

    def record(files: object, settings: Settings) -> list[Clone]:
        del files
        received.append(settings)
        return []

    monkeypatch.setattr("clonedigger.cli.find_clones", record)
    main(
        [
            str(INPUTS),
            "--size-threshold",
            "7",
            "--distance-threshold",
            "3",
            "--clustering-threshold",
            "9",
            "--hashing-depth",
            "4",
            "--force",
        ]
    )
    assert received == [Settings(7, 3, 9, 4, force=True)]
    main([str(INPUTS)])
    assert received[-1] == Settings()


def test_sarif_report(capsys: pytest.CaptureFixture[str]) -> None:
    """--format sarif prints a SARIF log with the clone of the recorded inputs."""
    assert main([str(INPUTS), "--format", "sarif"]) == 1
    log = json.loads(capsys.readouterr().out)
    assert len(log["runs"][0]["results"]) == 1
