# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""A project writes its options down under `[tool.clonedigger]`, and nothing is guessed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clonedigger.config import FILE_NAME, ConfigError, read_options

HELP = Path(__file__).parent / "data" / "help.txt"


def written_down(directory: Path, text: str) -> Path:
    """Write a pyproject.toml holding a `[tool.clonedigger]` table.

    Args:
        directory: Where to write the file.
        text: The lines of the table.

    Returns:
        The file written.
    """
    file = directory / FILE_NAME
    file.write_text(f"[tool.clonedigger]\n{text}\n", encoding="utf-8")
    return file


def test_nothing_written_down_anywhere_means_no_options(tmp_path: Path) -> None:
    """A directory with no pyproject.toml above it leaves every default in place."""
    assert not read_options(tmp_path)


def test_a_file_without_the_table_means_no_options(tmp_path: Path) -> None:
    """A pyproject.toml that says nothing about Clone Digger leaves the defaults."""
    (tmp_path / FILE_NAME).write_text('[project]\nname = "thing"\n', encoding="utf-8")
    assert not read_options(tmp_path)


def test_a_file_with_other_tools_only_means_no_options(tmp_path: Path) -> None:
    """A pyproject.toml holding other tools' tables leaves the defaults."""
    (tmp_path / FILE_NAME).write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    assert not read_options(tmp_path)


def test_every_option_is_read_under_the_name_argparse_knows(tmp_path: Path) -> None:
    """Each key becomes the option it names, with the value written down."""
    written_down(
        tmp_path,
        'format = "json"\n'
        "size-threshold = 8\n"
        "distance-threshold = 3\n"
        "clustering-threshold = 12\n"
        "hashing-depth = 2\n"
        "force = true\n"
        'func-prefixes = ["test_", "bench_"]\n'
        'ignore-dir = ["vendor", "migrations"]',
    )
    assert read_options(tmp_path) == {
        "format": "json",
        "size_threshold": 8,
        "distance_threshold": 3,
        "clustering_threshold": 12,
        "hashing_depth": 2,
        "force": True,
        "func_prefixes": ["test_", "bench_"],
        "ignore_dir": ["vendor", "migrations"],
    }


@pytest.mark.parametrize("name", ["text", "json", "sarif", "html"])
def test_every_report_format_can_be_written_down(tmp_path: Path, name: str) -> None:
    """Each format --format accepts is also accepted in the file."""
    written_down(tmp_path, f'format = "{name}"')
    assert read_options(tmp_path) == {"format": name}


def test_the_search_climbs_to_the_nearest_file(tmp_path: Path) -> None:
    """The file is looked for above the code, and the nearest one is the one read."""
    deep = tmp_path / "project" / "src" / "package"
    deep.mkdir(parents=True)
    written_down(tmp_path, "size-threshold = 99")
    written_down(tmp_path / "project", "size-threshold = 8")
    assert read_options(deep) == {"size_threshold": 8}


def test_a_file_named_is_read_beside_itself(tmp_path: Path) -> None:
    """Given a file to look at, the search starts in the directory holding it."""
    module = tmp_path / "thing.py"
    module.write_text("value = 1\n", encoding="utf-8")
    written_down(tmp_path, "size-threshold = 8")
    assert read_options(module) == {"size_threshold": 8}


def test_a_path_that_does_not_exist_is_read_beside_itself(tmp_path: Path) -> None:
    """A path naming nothing is treated as a file: the search starts in its directory."""
    written_down(tmp_path, "size-threshold = 8")
    assert read_options(tmp_path / "missing.py") == {"size_threshold": 8}


def test_the_search_stops_at_the_top_of_the_repository(tmp_path: Path) -> None:
    """What lies above the repository belongs to somebody else, and is not read."""
    repository = tmp_path / "repository"
    repository.mkdir()
    written_down(tmp_path, "size-threshold = 8")
    (repository / ".git").mkdir()
    assert not read_options(repository)
    # A worktree holds a .git file where a clone holds a directory.
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    assert not read_options(worktree)


def test_a_key_that_names_no_option_is_refused(tmp_path: Path) -> None:
    """An unknown key stops the reading, naming the file, the key and the options."""
    file = written_down(tmp_path, "size_threshold = 8")
    with pytest.raises(ConfigError) as refusal:
        read_options(tmp_path)
    message = str(refusal.value)
    assert str(file) in message
    assert "[tool.clonedigger]" in message
    assert 'has no option "size_threshold"' in message
    assert "the options are " in message


def test_the_options_the_file_takes_are_the_options_of_the_command_line(tmp_path: Path) -> None:
    """Every option --help lists, besides --help and --version, can be written down."""
    written_down(tmp_path, "not-an-option = 1")
    with pytest.raises(ConfigError) as refusal:
        read_options(tmp_path)
    offered = set(str(refusal.value).split("the options are ")[1].split(", "))
    listed = set(re.findall(r"--([a-z-]+)", HELP.read_text(encoding="utf-8")))
    assert offered == listed - {"help", "version"}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('size-threshold = "8"', '"size-threshold" must be a whole number'),
        ("size-threshold = true", '"size-threshold" must be a whole number'),
        ("distance-threshold = 1.5", '"distance-threshold" must be a whole number'),
        ("clustering-threshold = []", '"clustering-threshold" must be a whole number'),
        ('hashing-depth = "deep"', '"hashing-depth" must be a whole number'),
        ('force = "yes"', '"force" must be true or false'),
        ("force = 1", '"force" must be true or false'),
        ('ignore-dir = "vendor"', '"ignore-dir" must be a list of strings'),
        ("func-prefixes = [1]", '"func-prefixes" must be a list of strings'),
        ('format = "xml"', '"format" must be one of text, json, sarif, html'),
        ("format = 3", '"format" must be one of text, json, sarif, html'),
    ],
)
def test_a_value_of_the_wrong_kind_is_refused_with_the_kind_it_takes(
    tmp_path: Path, line: str, expected: str
) -> None:
    """A value an option does not take stops the reading, naming the key and the kind."""
    file = written_down(tmp_path, line)
    with pytest.raises(ConfigError, match=re.escape(expected)) as refusal:
        read_options(tmp_path)
    assert str(file) in str(refusal.value)
    assert "[tool.clonedigger]" in str(refusal.value)


def test_a_table_written_as_something_else_is_refused(tmp_path: Path) -> None:
    """`clonedigger` under `tool` that is not a table stops the reading."""
    (tmp_path / FILE_NAME).write_text("[tool]\nclonedigger = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"\[tool\.clonedigger\] must be a table of options"):
        read_options(tmp_path)


def test_a_file_that_is_not_valid_toml_is_refused(tmp_path: Path) -> None:
    """A pyproject.toml that TOML cannot read is named, with what TOML says about it."""
    file = tmp_path / FILE_NAME
    file.write_text("[tool.clonedigger\nforce = true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="is not valid TOML") as refusal:
        read_options(tmp_path)
    assert str(file) in str(refusal.value)
