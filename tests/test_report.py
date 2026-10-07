# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reports locate both copies of every clone, largest first."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from clonedigger import __version__
from clonedigger.detection import Clone
from clonedigger.python_frontend import Statement
from clonedigger.report import RULE_ID, as_json, as_sarif, as_text, findings
from clonedigger.tree import Node


def run(path: str, lines: range) -> tuple[Statement, ...]:
    """Build a run of one-line statements.

    Returns:
        One statement per line.
    """
    return tuple(Statement(Node("Pass", lines={line}), Path(path)) for line in lines)


SMALL = Clone(run("a.py", range(1, 6)), run("b.py", range(10, 15)), 2)
LARGE = Clone(run("c.py", range(1, 9)), run("d.py", range(20, 28)), 1)


def test_findings_come_largest_first_with_both_copies() -> None:
    """The longest clone comes first, and each finding names both copies."""
    first, second = findings([SMALL, LARGE])
    assert (str(first.first), str(first.second)) == ("c.py:1-8", "d.py:20-27")
    assert (str(second.first), str(second.second)) == ("a.py:1-5", "b.py:10-14")
    assert first.distance == 1


def test_text_has_one_line_per_clone_then_a_count() -> None:
    """Each clone on its own line, then how many were found."""
    assert as_text([SMALL, LARGE]).split("\n") == [
        "c.py:1-8  ~  d.py:20-27  (distance 1)",
        "a.py:1-5  ~  b.py:10-14  (distance 2)",
        "2 clones found.",
    ]


def test_json_is_indented_by_two() -> None:
    """The JSON is an array of findings, indented by two spaces."""
    expected = """[
  {
    "first": {
      "path": "a.py",
      "start": 1,
      "end": 5
    },
    "second": {
      "path": "b.py",
      "start": 10,
      "end": 14
    },
    "distance": 2
  }
]"""
    assert as_json([SMALL]) == expected


SCHEMA = json.loads((Path(__file__).parent / "data" / "sarif-schema-2.1.0.json").read_text())


def test_sarif_is_valid_against_the_official_schema() -> None:
    """The log validates against the OASIS SARIF 2.1.0 schema, with clones or without."""
    for clones in ([], [SMALL, LARGE]):
        jsonschema.validate(json.loads(as_sarif(clones)), SCHEMA)


def test_sarif_reports_each_clone_on_its_first_copy() -> None:
    """One result per clone, largest first, pointing to the other copy."""
    log = json.loads(as_sarif([SMALL, LARGE]))
    (sarif_run,) = log["runs"]
    assert log["version"] == "2.1.0"
    assert sarif_run["tool"]["driver"]["name"] == "clonedigger"
    assert [rule["id"] for rule in sarif_run["tool"]["driver"]["rules"]] == [RULE_ID]
    first, second = sarif_run["results"]
    assert first["ruleId"] == RULE_ID
    assert first["level"] == "warning"
    region = first["locations"][0]["physicalLocation"]
    assert region == {"artifactLocation": {"uri": "c.py"}, "region": {"startLine": 1, "endLine": 8}}
    other = first["relatedLocations"][0]
    assert other["id"] == 1
    assert other["physicalLocation"]["artifactLocation"]["uri"] == "d.py"
    assert other["physicalLocation"]["region"] == {"startLine": 20, "endLine": 27}
    assert first["message"]["text"] == (
        "Lines 1-8 are a copy of [d.py:20-27](1), up to a difference of 1."
    )
    assert second["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "a.py"


def test_sarif_is_written_as_recorded() -> None:
    """Every text of the log, its layout included, is the recorded one.

    After a deliberate change, regenerate tests/data/sarif.json from
    as_sarif([SMALL, LARGE]), with the tool's version written <version>.
    """
    written = json.loads(as_sarif([SMALL, LARGE]))
    assert written["runs"][0]["tool"]["driver"].pop("version") == __version__
    expected = (Path(__file__).parent / "data" / "sarif.json").read_text()
    layout = json.loads(as_sarif([SMALL, LARGE]))
    layout["runs"][0]["tool"]["driver"]["version"] = "<version>"
    assert json.dumps(layout, indent=2) + "\n" == expected
    assert as_sarif([SMALL, LARGE]).startswith('{\n  "$schema"')
