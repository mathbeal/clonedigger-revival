# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""What a project writes down for itself, under `[tool.clonedigger]` of its pyproject.

A project keeps its own thresholds and the directories it skips in the file it already
has, instead of repeating them in every command line and every CI job. Every option of
the command line can be written there, under the name it has on the command line
without the dashes in front, and what the command line says wins over it.

Nothing is guessed: a key that names no option, and a value of a kind an option does
not take, stop the command with a message naming the file and the key.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class ConfigError(ValueError):
    """What a project wrote down cannot be used; the message says where and why."""


class _MismatchError(Exception):
    """A value is not of the kind its option takes; the message says which kind."""


# The file read, and the table read in it.
FILE_NAME = "pyproject.toml"
TABLE_NAME = "[tool.clonedigger]"

# What marks the top of a repository: a directory in a clone, a file in a worktree.
REPOSITORY_MARK = ".git"

# What --format accepts, on the command line and in the file.
REPORT_FORMATS: Final = ("text", "json", "sarif", "html")


def _whole_number(value: object) -> int:
    """Read a threshold, written as a whole number.

    Args:
        value: What the file holds.

    Returns:
        The number.

    Raises:
        _MismatchError: If the value is not a whole number; `true` is not 1 here.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "must be a whole number"
        raise _MismatchError(msg)
    return value


def _flag(value: object) -> bool:
    """Read an option that is either on or off.

    Args:
        value: What the file holds.

    Returns:
        Whether it is on.

    Raises:
        _MismatchError: If the value is not `true` or `false`.
    """
    if not isinstance(value, bool):
        msg = "must be true or false"
        raise _MismatchError(msg)
    return value


def _words(value: object) -> list[str]:
    """Read an option that names several things, written as a list.

    Args:
        value: What the file holds.

    Returns:
        The words, in the order written, as a list of their own: argparse appends to
        the list it is given as a default.

    Raises:
        _MismatchError: If the value is not a list of strings.
    """
    if not isinstance(value, list) or not all(isinstance(word, str) for word in value):
        msg = "must be a list of strings"
        raise _MismatchError(msg)
    return list(value)


def _report_format(value: object) -> str:
    """Read the name of a report format.

    Args:
        value: What the file holds.

    Returns:
        The name.

    Raises:
        _MismatchError: If the value names no report format.
    """
    if not isinstance(value, str) or value not in REPORT_FORMATS:
        names = ", ".join(REPORT_FORMATS)
        msg = f"must be one of {names}"
        raise _MismatchError(msg)
    return value


# Every option of the command line, by the key that writes it down: the dashes in front
# dropped, the name kept. `tests/test_config.py` checks that none is missing or extra.
_READERS: Final[dict[str, Callable[[object], object]]] = {
    "format": _report_format,
    "size-threshold": _whole_number,
    "distance-threshold": _whole_number,
    "clustering-threshold": _whole_number,
    "hashing-depth": _whole_number,
    "force": _flag,
    "func-prefixes": _words,
    "ignore-dir": _words,
}


def _nearest_file(path: Path) -> Path | None:
    """Look for a pyproject.toml at the code being read, then above it.

    The search climbs, since a project is configured at its top and read by the
    directory, and stops at the top of the repository: what lies above belongs to
    somebody else.

    Args:
        path: The first file or directory named on the command line.

    Returns:
        The file found, or None when there is none to read.
    """
    start = path.resolve()
    for directory in (start, *start.parents):
        candidate = directory / FILE_NAME
        if candidate.is_file():
            return candidate
        if (directory / REPOSITORY_MARK).exists():
            return None
    return None


def _read_table(file: Path) -> dict[str, object]:
    """Read the options written down in one pyproject.toml.

    Args:
        file: The pyproject.toml found.

    Returns:
        The options, under the names argparse knows them by.

    Raises:
        ConfigError: If the file cannot be read, if it is not valid TOML, if a table is
            written as something else, if a key names no option, or if a value is not of
            the kind its option takes.
    """
    try:
        with file.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        msg = f"{file} is not valid TOML: {error}"
        raise ConfigError(msg) from error
    except OSError as error:
        msg = f"{file} cannot be read: {error}"
        raise ConfigError(msg) from error
    tool: object = document.get("tool", {})
    if not isinstance(tool, dict):
        msg = f"{file}: [tool] must be a table of tools"
        raise ConfigError(msg)
    table: object = tool.get("clonedigger", {})
    if not isinstance(table, dict):
        msg = f"{file}: {TABLE_NAME} must be a table of options"
        raise ConfigError(msg)
    options: dict[str, object] = {}
    for key, value in table.items():
        reader = _READERS.get(key)
        if reader is None:
            known = ", ".join(sorted(_READERS))
            msg = f'{file}: {TABLE_NAME} has no option "{key}"; the options are {known}'
            raise ConfigError(msg)
        try:
            options[key.replace("-", "_")] = reader(value)
        except _MismatchError as error:
            msg = f'{file}: {TABLE_NAME} "{key}" {error}'
            raise ConfigError(msg) from error
    return options


def read_options(path: Path) -> dict[str, object]:
    """Read the options a project wrote down for the code being read.

    A file that cannot be used raises `ConfigError`, from `_read_table`.

    Args:
        path: The first file or directory named on the command line.

    Returns:
        The options, under the names argparse knows them by; empty when the project
        wrote nothing down.
    """
    file = _nearest_file(path)
    if file is None:
        return {}
    return _read_table(file)
