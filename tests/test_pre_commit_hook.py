# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""The hook this repository offers to a project that uses pre-commit.

A project names the repository in its own `.pre-commit-config.yaml`, and pre-commit
reads `.pre-commit-hooks.yaml` here to know what to run. Its schema says what that file
may hold: `load_manifest` reads the file the way pre-commit does, and refuses a required
key left out, a language or a file type it does not know, and a value of the wrong kind.
"""

from __future__ import annotations

from pathlib import Path

from pre_commit.clientlib import load_manifest

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / ".pre-commit-hooks.yaml"
REPOSITORY = "https://github.com/mathbeal/clonedigger-revival"


def read_hooks() -> list[dict[str, object]]:
    """Read the manifest of the repository against pre-commit's own schema.

    Returns:
        The hooks it offers, in the order they are written.
    """
    hooks: list[dict[str, object]] = load_manifest(str(MANIFEST))
    return hooks


def test_the_manifest_holds_the_one_hook_the_readme_documents() -> None:
    """pre-commit's schema accepts the manifest, which offers the `clonedigger` hook."""
    assert [hook["id"] for hook in read_hooks()] == ["clonedigger"]


def test_the_hook_runs_the_command_on_the_python_files_it_is_given() -> None:
    """The hook runs `clonedigger`, built from the sources, on the Python files named."""
    (hook,) = read_hooks()
    assert hook["entry"] == "clonedigger"
    assert hook["language"] == "python"
    assert hook["types"] == ["python"]
    assert hook["pass_filenames"] is True


def test_the_readme_example_names_this_repository_and_that_hook() -> None:
    """The `.pre-commit-config.yaml` of the README uses the repository and the hook id."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (hook,) = read_hooks()
    assert f"- repo: {REPOSITORY}\n" in readme
    assert f"- id: {hook['id']}\n" in readme
