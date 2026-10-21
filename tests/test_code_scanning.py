# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The example workflow that sends the SARIF report to GitHub code scanning.

`examples/code-scanning.yml` is meant to be copied into a project, and
`docs/github-code-scanning.md` explains it line by line. Both are checked here: the
page shows the file as it is, the file asks for the two permissions the page says it
asks for, its actions are pinned to a commit, and the report it uploads is the one it
wrote. zizmor audits the file itself, under `just hygiene` and in CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / "examples" / "code-scanning.yml"
GUIDE = ROOT / "docs" / "github-code-scanning.md"
REPORT = ROOT / "examples" / "report.sarif"
SCHEMA = ROOT / "tests" / "data" / "sarif-schema-2.1.0.json"
# An action named, the 40 characters of the commit it is pinned to, and the version
# that commit stood for when it was written down.
PINNED = re.compile(r"^\s*- uses: (\S+)@([0-9a-f]{40})\s+# (v\S+)$", re.MULTILINE)
# The file the command writes the SARIF to, from the redirection of the run step.
WRITTEN_TO = re.compile(r"> (\S+\.sarif)\b")


def workflow() -> dict[str, Any]:
    """Read the example workflow as GitHub Actions reads it.

    Returns:
        What the YAML of `examples/code-scanning.yml` holds.
    """
    read: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return read


def the_one_job() -> dict[str, Any]:
    """Read the single job of the example workflow, which holds no other.

    Returns:
        The job, with its permissions and its steps.
    """
    (job,) = workflow()["jobs"].values()
    read: dict[str, Any] = job
    return read


def test_the_guide_shows_the_workflow_byte_for_byte() -> None:
    """The YAML block of docs/github-code-scanning.md is the committed file, exactly."""
    page = GUIDE.read_text(encoding="utf-8")
    shown = page.split("```yaml\n")[1].split("```")[0]
    assert shown == WORKFLOW.read_text(encoding="utf-8")


def test_every_action_is_pinned_to_a_commit_with_its_version() -> None:
    """Each `uses:` names a 40-character commit, with the version it stood for."""
    text = WORKFLOW.read_text(encoding="utf-8")
    pinned = PINNED.findall(text)
    assert [action for action, _, _ in pinned] == [
        "actions/checkout",
        "astral-sh/setup-uv",
        "github/codeql-action/upload-sarif",
    ]
    assert text.count("uses:") == len(pinned)


def test_the_job_asks_for_the_two_permissions_it_needs_and_no_other() -> None:
    """Nothing is granted by default, and the job takes back only what it uses."""
    assert workflow()["permissions"] == {}
    assert the_one_job()["permissions"] == {"contents": "read", "security-events": "write"}


def test_the_report_written_is_the_report_uploaded() -> None:
    """The step writes a SARIF report, and the upload step is given that same file."""
    run, upload = the_one_job()["steps"][2:]
    assert "--format sarif" in run["run"]
    assert WRITTEN_TO.findall(run["run"]) == [upload["with"]["sarif_file"]]


def test_the_upload_puts_the_results_in_their_own_category() -> None:
    """The results are uploaded under a category, apart from another tool's."""
    assert the_one_job()["steps"][-1]["with"]["category"] == "clonedigger"


def test_the_report_the_guide_sends_validates_against_the_sarif_schema() -> None:
    """The committed example report, what the workflow uploads, is valid SARIF 2.1.0."""
    jsonschema.validate(
        json.loads(REPORT.read_text(encoding="utf-8")),
        json.loads(SCHEMA.read_text(encoding="utf-8")),
    )


def test_the_guide_quotes_the_first_result_of_the_example_report() -> None:
    """The alert shown in the guide is the first result of examples/report.sarif."""
    first = json.loads(REPORT.read_text(encoding="utf-8"))["runs"][0]["results"][0]
    page = GUIDE.read_text(encoding="utf-8")
    assert f'"text": "{first["message"]["text"]}"' in page
    assert f'"ruleId": "{first["ruleId"]}"' in page
    assert f'"level": "{first["level"]}"' in page
