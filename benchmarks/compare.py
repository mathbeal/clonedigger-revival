# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compare Clone Digger with pylint `duplicate-code` and jscpd on well-known projects.

Each project is a pinned source release from PyPI, checked against its SHA-256 before it
is unpacked. Each tool reads the project's package only, its tests left out, and keeps
copies of at least 5 lines. For each run: the wall-clock time, the largest memory the
process held, and the clones found, counted as pairs (three copies of one block make
three pairs, as Clone Digger reports them).

Run it with `just compare` (it needs Node.js for jscpd); the table it prints goes into
the README, and the raw figures into benchmarks/results.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

HERE: Final = Path(__file__).parent
CACHE: Final = Path(
    os.environ.get("CLONEDIGGER_BENCH_CACHE", Path.home() / ".cache" / "clonedigger-bench")
)
JSCPD: Final = "4.0.5"
PYPI: Final = "https://files.pythonhosted.org/packages"
MIN_LINES: Final = 5
# A tool that runs longer than this on one project is stopped, and reported so.
TIMEOUT: Final = 1800


@dataclass(frozen=True)
class Project:
    """A source release of a well-known project, pinned.

    Attributes:
        name: Its name on PyPI.
        version: The release measured.
        location: Where PyPI keeps its source archive, under `PYPI`.
        archive: The name of the archive.
        sha256: The digest the archive must have.
        package: The directory of its package inside the archive.
    """

    name: str
    version: str
    location: str
    archive: str
    sha256: str
    package: str

    @property
    def url(self) -> str:
        """Where PyPI serves the source archive."""
        return f"{PYPI}/{self.location}/{self.archive}"


PROJECTS: Final = (
    Project(
        "requests",
        "2.34.2",
        "ac/c3/e2a2b89f2d3e2179abd6d00ebd70bff6273f37fb3e0cc209f48b39d00cbf",
        "requests-2.34.2.tar.gz",
        "f288924cae4e29463698d6d60bc6a4da69c89185ad1e0bcc4104f584e960b9ed",
        "src/requests",
    ),
    Project(
        "httpx",
        "0.28.1",
        "b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956",
        "httpx-0.28.1.tar.gz",
        "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc",
        "httpx",
    ),
    Project(
        "Flask",
        "3.1.3",
        "26/00/35d85dcce6c57fdc871f3867d465d780f302a175ea360f62533f12b27e2b",
        "flask-3.1.3.tar.gz",
        "0ef0e52b8a9cd932855379197dd8f94047b359ca0a78695144304cb45f87c9eb",
        "src/flask",
    ),
    Project(
        "click",
        "8.5.0",
        "c7/0e/7fa0ef50764b67090eca4114772a2abf8b6148198475e54c660b97caeee6",
        "click-8.5.0.tar.gz",
        "ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34",
        "src/click",
    ),
    Project(
        "FastAPI",
        "0.142.4",
        "b8/2c/d69ce63c27bf9c5e574ab425118390102924503b4b3cdf33c07a69744dd2",
        "fastapi-0.142.4.tar.gz",
        "7fe2e254a0a948b88f432b02b8f627463285248233bba0998ed9640191e2ff57",
        "fastapi",
    ),
    Project(
        "FastMCP",
        "4.0.11",
        "e4/ca/e76fde836e6e443f49b1a16ad91fa71715ec220141261a290c9241024857",
        "fastmcp-4.0.11.tar.gz",
        "55fc7b8e25d4f8365818ba93f7008d1b6e646ce7fe8ae49342687243ccbef9f2",
        "fastmcp_slim/fastmcp",
    ),
    Project(
        "rich",
        "15.0.0",
        "c0/8f/0722ca900cc807c13a6a0c696dacf35430f72e0ec571c4275d2371fca3e9",
        "rich-15.0.0.tar.gz",
        "edd07a4824c6b40189fb7ac9bc4c52536e9780fbbfbddf6f1e2502c31b068c36",
        "rich",
    ),
    Project(
        "SQLAlchemy",
        "2.1.4",
        "1f/44/311bac6b6ef81e4dfd0287d04900108b1f5c00c9761dd3c0a2b7b9d0f86b",
        "sqlalchemy-2.1.4.tar.gz",
        "7bd7ad604487daa7eab8716471c29a7185f17b5287ce73bb7bc79fea050d8cfd",
        "lib/sqlalchemy",
    ),
    Project(
        "Django",
        "6.1.2",
        "89/24/20d187a22ac821288b53c53b8f696019dcb0c7b4f973f052ade19392c74d",
        "django-6.1.2.tar.gz",
        "a1e92451ccb8b514e91bbb3b6d186d20b4030558f116b5d9de6535455ff210b7",
        "django",
    ),
)


@dataclass(frozen=True)
class Run:
    """One tool on one project.

    Attributes:
        tool: The tool.
        seconds: The wall-clock time.
        megabytes: The largest memory the process held, in MB.
        pairs: The clones found, counted as pairs; None if the run did not finish.
        copied: How many lines of the project lie in at least one copy.
    """

    tool: str
    seconds: float
    megabytes: float
    pairs: int | None
    copied: int = 0


def fetch(project: Project) -> Path:
    """Download and unpack a project once, after checking its digest.

    Args:
        project: The project.

    Returns:
        The directory of its package.

    Raises:
        ValueError: If the archive is not the one pinned.
    """
    archive = CACHE / project.archive
    if not archive.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        # A pinned https URL of PyPI, and the digest is checked below.
        with urllib.request.urlopen(project.url, timeout=120) as answer:
            archive.write_bytes(answer.read())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != project.sha256:
        archive.unlink()
        msg = f"{archive.name}: SHA-256 {digest}, expected {project.sha256}"
        raise ValueError(msg)
    root = CACHE / f"{project.name}-{project.version}"
    if not root.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(root, filter="data")
    (top,) = root.iterdir()
    return top / project.package


def measure(tool: str, command: Sequence[str], cwd: Path) -> tuple[float, float, str] | None:
    """Run a command, timing it and reading the largest memory it held.

    Args:
        tool: The name of the tool, for the messages.
        command: The command.
        cwd: Where to run it.

    Returns:
        The seconds, the megabytes and the standard output; None if it ran out of time.
    """
    start = time.perf_counter()
    deadline = start + TIMEOUT
    # The three tools, from this virtual environment or the cache: nothing untrusted.
    with (
        tempfile.TemporaryFile() as out,
        subprocess.Popen(command, cwd=cwd, stdout=out, stderr=subprocess.DEVNULL) as process,
    ):
        # wait4, not wait: it also gives the resources the process used.
        pid, _, usage = os.wait4(process.pid, os.WNOHANG)
        while not pid:
            if time.perf_counter() > deadline:
                process.kill()
                os.wait4(process.pid, 0)
                sys.stderr.write(f"  {tool}: stopped after {TIMEOUT} s\n")
                return None
            time.sleep(0.05)
            pid, _, usage = os.wait4(process.pid, os.WNOHANG)
        seconds = time.perf_counter() - start
        # ru_maxrss is in bytes on macOS, in kilobytes on Linux.
        scale = 1 if sys.platform == "darwin" else 1024
        out.seek(0)
        return seconds, usage.ru_maxrss * scale / 1e6, out.read().decode("utf-8", "replace")


def clone_digger(package: Path) -> Run:
    """Run Clone Digger, with its defaults.

    Args:
        package: The directory to read.

    Returns:
        The measures, and its clones.
    """
    # -P: the directory read must not shadow a module, as flask/json shadows json.
    command = [sys.executable, "-P", "-m", "clonedigger", "--format", "json", str(package)]
    result = measure("clonedigger", command, CACHE)
    if result is None:
        return Run("clonedigger", TIMEOUT, 0, None)
    seconds, megabytes, output = result
    found = json.loads(output)
    places = {
        (copy["path"], line)
        for finding in found
        for copy in (finding["first"], finding["second"])
        for line in range(copy["start"], copy["end"] + 1)
    }
    return Run("clonedigger", seconds, megabytes, len(found), len(places))


# A copy in a pylint message: ==module:[start:end]. A module name can hold hyphens.
COPY: Final = r"^==([^:\s]+):\[(\d+):(\d+)\]"
# A message names two copies at least: fewer, and it was misread.
PAIR: Final = 2


def pylint(package: Path) -> Run:
    """Run pylint's `duplicate-code` check only, at 5 lines.

    Args:
        package: The directory to read.

    Returns:
        The measures, and its clones as pairs: a message naming n places is n(n-1)/2.

    Raises:
        ValueError: If a message names fewer than two copies that can be read.
    """
    command = [
        sys.executable,
        "-P",
        "-m",
        "pylint",
        "--rcfile=/dev/null",
        "--disable=all",
        "--enable=duplicate-code",
        f"--min-similarity-lines={MIN_LINES}",
        "--output-format=json",
        str(package),
    ]
    result = measure("pylint", command, CACHE)
    if result is None:
        return Run("pylint", TIMEOUT, 0, None)
    seconds, megabytes, output = result
    pairs = 0
    places: set[tuple[str, int]] = set()
    for message in json.loads(output or "[]"):
        # One line per copy: ==module:[start:end], lines counted from 0, the end left out.
        copies = re.findall(COPY, message["message"], flags=re.MULTILINE)
        if len(copies) < PAIR:
            msg = f"cannot read the copies of: {message['message'][:200]}"
            raise ValueError(msg)
        pairs += len(copies) * (len(copies) - 1) // 2
        for module, start, end in copies:
            places.update((module, line) for line in range(int(start) + 1, int(end) + 1))
    return Run("pylint", seconds, megabytes, pairs, len(places))


def jscpd(package: Path) -> Run:
    """Run jscpd on the Python files, at 5 lines.

    Args:
        package: The directory to read.

    Returns:
        The measures, and its clones (each one a pair).
    """
    binary = CACHE / "node_modules" / ".bin" / "jscpd"
    if not binary.exists():
        # npm, found on the PATH, installs the pinned version into the cache.
        subprocess.run(
            ["npm", "install", "--prefix", str(CACHE), f"jscpd@{JSCPD}"],
            check=True,
            capture_output=True,
        )
    with tempfile.TemporaryDirectory() as report:
        command = [
            str(binary),
            str(package),
            "--format",
            "python",
            "--min-lines",
            str(MIN_LINES),
            "--reporters",
            "json",
            "--output",
            report,
            "--silent",
        ]
        result = measure("jscpd", command, CACHE)
        if result is None:
            return Run("jscpd", TIMEOUT, 0, None)
        seconds, megabytes, _ = result
        found = json.loads((Path(report) / "jscpd-report.json").read_text())["duplicates"]
    places = {
        (copy["name"], line)
        for duplicate in found
        for copy in (duplicate["firstFile"], duplicate["secondFile"])
        for line in range(copy["start"], copy["end"] + 1)
    }
    return Run("jscpd", seconds, megabytes, len(found), len(places))


def lines_of(package: Path) -> int:
    """Count the lines of the Python files of a package.

    Args:
        package: Its directory.

    Returns:
        Every line, blank ones and comments included.
    """
    return sum(len(path.read_bytes().splitlines()) for path in package.rglob("*.py"))


def versions() -> dict[str, str]:
    """Name the version of every tool and of the machine.

    Returns:
        The versions, by name.
    """
    return {
        "clonedigger": version("clonedigger-revival"),
        "pylint": version("pylint"),
        "jscpd": JSCPD,
        "python": platform.python_version(),
        "machine": f"{platform.system()} {platform.machine()}",
    }


def cell(run: Run, lines: int) -> str:
    """Write one run for the table.

    Args:
        run: The run.
        lines: The lines of the project.

    Returns:
        Its pairs, the share of the lines in a copy, its time and its memory.
    """
    if run.pairs is None:
        return f"stopped after {TIMEOUT // 60} min"
    share = 100 * run.copied / lines
    return f"{run.pairs} · {share:.1f} % · {run.seconds:.1f} s · {run.megabytes:.0f} MB"


def main(names: Sequence[str]) -> None:
    """Measure the projects, print the table and write the raw figures.

    Args:
        names: The projects to measure, by name; all of them when empty. Only a full
            run writes benchmarks/results.json.
    """
    if shutil.which("npm") is None:
        sys.exit("jscpd needs Node.js: npm was not found.")
    chosen = [project for project in PROJECTS if not names or project.name in names]
    rows: list[dict[str, object]] = []
    for project in chosen:
        package = fetch(project)
        sys.stderr.write(f"{project.name} {project.version}\n")
        runs = [clone_digger(package), pylint(package), jscpd(package)]
        lines = lines_of(package)
        rows.append({**asdict(project), "lines": lines, "runs": [asdict(run) for run in runs]})
        cells = " | ".join(cell(run, lines) for run in runs)
        sys.stdout.write(f"| {project.name} {project.version} | {lines:,} | {cells} |\n")
        sys.stdout.flush()
    if not names:
        report = {"versions": versions(), "projects": rows}
        (HERE / "results.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
