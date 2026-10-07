# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0, clonedigger.py)
# Copyright 2026 Mathieu Béal (modified 2026-10-07: rewritten with argparse)
# SPDX-License-Identifier: GPL-3.0-or-later

"""The `clonedigger` command: find the clones in Python files and directories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from clonedigger.detection import Settings, find_clones
from clonedigger.python_frontend import read_source
from clonedigger.report import as_json, as_text

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

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
    parser.add_argument("--format", choices=("text", "json"), default="text")
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
        default="",
        help="comma-separated prefixes of function names to leave out, such as test_",
    )
    parser.add_argument("--ignore-dir", action="append", default=[], help="directory name to skip")
    return parser


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
                if not ignored or not set(file.relative_to(path).parts[:-1]) & set(ignored)
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
    prefixes = tuple(prefix.strip() for prefix in options.func_prefixes.split(",") if prefix)
    files: list[SourceFile] = []
    status = 0
    for path in python_files(options.paths, options.ignore_dir):
        try:
            files.append(read_source(path, path.read_text(encoding="utf-8"), prefixes))
        except (OSError, SyntaxError, UnicodeDecodeError) as error:
            sys.stderr.write(f"clonedigger: cannot read {path}: {error}\n")
            status = 2
    settings = Settings(
        size_threshold=options.size_threshold,
        distance_threshold=options.distance_threshold,
        clustering_threshold=options.clustering_threshold,
        hashing_depth=options.hashing_depth,
        force=options.force,
    )
    clones = find_clones(files, settings)
    sys.stdout.write((as_json(clones) if options.format == "json" else as_text(clones)) + "\n")
    return status or (1 if clones else 0)
