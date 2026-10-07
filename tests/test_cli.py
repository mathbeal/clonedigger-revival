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
    found = [path.relative_to(tmp_path).as_posix() for path in python_files([tmp_path], ["venv"])]
    assert found == ["a.py", "pkg/b.py"]
    assert len(list(python_files([tmp_path], []))) == 3


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python -m clonedigger runs the command and exits with its status."""
    monkeypatch.setattr(sys, "argv", ["clonedigger", str(INPUTS)])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("clonedigger", run_name="__main__")
    assert exit_info.value.code == 1
