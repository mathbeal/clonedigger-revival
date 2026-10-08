# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, clonedigger.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: rewritten with argparse)
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `clonedigger` command: find the clones in Python files and directories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from clonedigger.detection import Settings, find_clones
from clonedigger.html_report import as_html
from clonedigger.python_frontend import read_source
from clonedigger.report import as_json, as_sarif, as_text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from clonedigger.detection import Clone
    from clonedigger.python_frontend import SourceFile


def _parser() -> argparse.ArgumentParser:
    defaults = Settings()
    parser = argparse.ArgumentParser(
        prog="clonedigger",
        description=(
            "Find duplicated code by anti-unification. Clone Digger by Peter Bulychev, "
            "with Marius Minea; ported to Python 3."
        ),
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Python files or directories")
    parser.add_argument(
        "--format",
        choices=(*REPORTS, "html"),
        default="text",
        help="report format (default text); html is one page, to save and open",
    )
    parser.add_argument(
        "--size-threshold",
        type=int,
        default=defaults.size_threshold,
        help="fewest lines a clone spans (default %(default)s)",
    )
    parser.add_argument(
        "--distance-threshold",
        type=int,
        default=defaults.distance_threshold,
        help="largest difference between the two copies (default %(default)s)",
    )
    parser.add_argument(
        "--clustering-threshold",
        type=int,
        default=defaults.clustering_threshold,
        help="largest cost of joining a cluster (default %(default)s)",
    )
    parser.add_argument(
        "--hashing-depth",
        type=int,
        default=defaults.hashing_depth,
        help="how deep statements are hashed into buckets (default %(default)s)",
    )
    parser.add_argument("--force", action="store_true", help="keep long runs of similar statements")
    parser.add_argument(
        "--func-prefixes",
        type=_prefixes,
        default=(),
        help="comma-separated prefixes of function names to leave out, such as test_",
    )
    parser.add_argument("--ignore-dir", action="append", default=[], help="directory name to skip")
    return parser


# What --format names, and the function that writes it.
REPORTS: Final[dict[str, Callable[[Sequence[Clone]], str]]] = {
    "text": as_text,
    "json": as_json,
    "sarif": as_sarif,
}


def _syntax_hint() -> str:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (
        f"  This Python ({version}) reads the syntax of Python {version} and earlier: code "
        "written for a later Python must be read with that Python, and Python 2 code is "
        "not read."
    )


def _prefixes(text: str) -> tuple[str, ...]:
    return tuple(prefix.strip() for prefix in text.split(",") if prefix.strip())


def python_files(paths: Sequence[Path], ignored: Sequence[str]) -> Iterator[Path]:
    """List the Python files of the given files and directories, in a stable order.

    Args:
        paths: Files and directories.
        ignored: Directory names to skip anywhere below the given directories.

    Yields:
        Each `.py` file.
    """
    for path in paths:
        if path.is_dir():
            yield from sorted(
                file
                for file in path.rglob("*.py")
                if not set(file.relative_to(path).parts[:-1]) & set(ignored)
            )
        else:
            yield path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command.

    Args:
        argv: The arguments, without the program name; those of the process if left out.

    Returns:
        The exit status: 0 with no clone, 1 when clones are found, 2 on an unreadable
        file.
    """
    options = _parser().parse_args(argv)
    files: list[SourceFile] = []
    unreadable = False  # pragma: no mutate - None would be just as false
    for path in python_files(options.paths, options.ignore_dir):
        try:
            text = path.read_text(encoding="utf-8")  # pragma: no mutate - "UTF-8" is the same
            files.append(read_source(path, text, options.func_prefixes))
        except SyntaxError as error:
            sys.stderr.write(f"clonedigger: cannot parse {path}: {error}\n{_syntax_hint()}\n")
            unreadable = True
        except (OSError, UnicodeDecodeError) as error:
            sys.stderr.write(f"clonedigger: cannot read {path}: {error}\n")
            unreadable = True
    settings = Settings(
        size_threshold=options.size_threshold,
        distance_threshold=options.distance_threshold,
        clustering_threshold=options.clustering_threshold,
        hashing_depth=options.hashing_depth,
        force=options.force,
    )
    clones = find_clones(files, settings)
    if options.format == "html":
        sources = {file.path: file.lines for file in files}
        sys.stdout.write(as_html(clones, sources))
    else:
        sys.stdout.write(REPORTS[options.format](clones) + "\n")
    if unreadable:
        return 2
    return 1 if clones else 0
