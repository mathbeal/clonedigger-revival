# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The reports committed under examples/ are the ones the tool writes today.

They are read by whoever wants to see the output before installing anything, so a
change of what the tool writes must reach them: `just examples` writes them again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clonedigger.cli import main
from clonedigger.config import REPORT_FORMATS

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
# The path given on the command line, which the reports hold, with its forward slash on
# every system: `just examples` runs from the top of the repository.
EXAMPLE = "examples/shipping.py"
# The file each format is written to, as `just examples` names them.
SUFFIXES = {"text": "txt", "json": "json", "sarif": "sarif", "html": "html"}


def report(report_format: str, capsys: pytest.CaptureFixture[str]) -> str:
    """Run the command on the example and give back what it wrote.

    Args:
        report_format: The value of --format.
        capsys: The fixture holding what the command wrote.

    Returns:
        The report, exactly as `just examples` redirects it to its file.
    """
    assert main([EXAMPLE, "--format", report_format]) == 1
    return capsys.readouterr().out


@pytest.mark.parametrize("report_format", SUFFIXES)
def test_the_committed_report_is_what_the_command_writes(
    report_format: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each report of examples/ is byte for byte what the command writes today."""
    monkeypatch.chdir(ROOT)
    committed = (EXAMPLES / f"report.{SUFFIXES[report_format]}").read_text(encoding="utf-8")
    assert report(report_format, capsys) == committed


def test_every_format_of_the_command_has_its_report() -> None:
    """The example is written in every format --format offers, and in no other."""
    assert set(SUFFIXES) == set(REPORT_FORMATS)
    assert sorted(path.name for path in EXAMPLES.glob("report.*")) == [
        f"report.{suffix}" for suffix in sorted(SUFFIXES.values())
    ]


def test_the_example_readme_shows_the_text_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run shown in examples/README.md is the text report, line for line."""
    monkeypatch.chdir(ROOT)
    shown = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    assert report("text", capsys) in shown
