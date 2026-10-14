# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Draw the sample of reported pairs that precision is measured on.

Two of the pinned projects of `just compare`, one library and one framework, are read
with the defaults of the tool, and the same number of pairs is drawn at random from each,
so that neither project drowns the other. The seed is written down: the draw is the same
at every run, and the file it writes is committed.

The paths are relative to the cache the archives are unpacked into, so that one `--root`
reaches the files of both projects:

    just label --report benchmarks/sample.json --root ~/.cache/clonedigger-bench

The sample is a report of pairs, the format `just label` reads. Which pairs are
duplicated code is then measured by `just precision`, which needs neither this script nor
the network.

Run it with `just sample`. It needs the archives, downloaded once from PyPI and checked
against their SHA-256, as `just compare` does.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Final

from benchmarks.compare import CACHE, PROJECTS, fetch
from benchmarks.label import read_pairs
from benchmarks.precision import draw

if TYPE_CHECKING:
    from benchmarks.compare import Project
    from benchmarks.precision import Pair

HERE: Final = Path(__file__).parent
SAMPLE: Final = HERE / "sample.json"
# The two projects drawn from, by their name in `just compare`: httpx, a library of a few
# thousand lines, and Django, a framework of a hundred and sixty thousand.
DRAWN_FROM: Final = ("httpx", "Django")
# How many pairs are drawn from each, and the seed that makes the draw repeatable. The
# seed is 1, the first one tried: a seed chosen after seeing the figure chooses the
# figure.
PER_PROJECT: Final = 30
SEED: Final = 1
# The detection finds clones: it answers 1, not 0, and above that it failed.
FOUND: Final = 1


def pinned(name: str) -> Project:
    """Find a project of `just compare` by its name.

    Args:
        name: Its name on PyPI.

    Returns:
        The pinned release.

    Raises:
        ValueError: No pinned project goes by that name.
    """
    for project in PROJECTS:
        if project.name == name:
            return project
    msg = f"{name} is not one of the pinned projects: {', '.join(p.name for p in PROJECTS)}"
    raise ValueError(msg)


def detect(package: Path) -> list[Pair]:
    """Run the detection on a package and read the pairs it reports.

    Args:
        package: The directory of the package, inside the cache.

    Returns:
        The two copies of each pair, their paths relative to the cache.

    Raises:
        RuntimeError: The detection did not run to its end.
    """
    # -P: the directory read must not shadow a module, as flask/json shadows json.
    command = [sys.executable, "-P", "-m", "clonedigger", "--format", "json", str(package)]
    with tempfile.TemporaryDirectory() as directory:
        report = Path(directory) / "report.json"
        with report.open("w", encoding="utf-8") as sink:
            # This virtual environment, on the archives `just compare` checked.
            status = subprocess.run(command, cwd=CACHE, stdout=sink, check=False).returncode
        if status > FOUND:
            msg = f"clonedigger on {package} stopped with status {status}"
            raise RuntimeError(msg)
        return read_pairs(report)


def main() -> None:
    """Draw the sample from each project in turn and write it down."""
    sample: list[Pair] = []
    for name in DRAWN_FROM:
        package = fetch(pinned(name)).relative_to(CACHE)
        pairs = detect(package)
        sys.stderr.write(f"{name}: {len(pairs)} pairs reported, {PER_PROJECT} drawn\n")
        sample.extend(draw(pairs, PER_PROJECT, SEED))
    records = [{"first": asdict(first), "second": asdict(second)} for first, second in sample]
    SAMPLE.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
