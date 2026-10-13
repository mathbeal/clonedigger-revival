# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Judge the pairs a report found, one by one, and write the verdicts down.

Precision is the share of the pairs reported that are duplicated code to a reader.
Measuring it needs a sample judged by hand: this tool reads a report written by
`clonedigger --format json`, shows the two copies of each pair side by side, and records
the verdict.

The verdicts are JSON Lines, one record per pair, each record standing on its own:

    {"version": 1, "first": {"path": "a.py", "start": 10, "end": 20},
     "second": {"path": "b.py", "start": 30, "end": 40},
     "clone": true, "reason": "same loop, other names"}

`version` is the version of this format, `FORMAT_VERSION`; reading refuses a version it
does not know, so that a sample judged under one format is never counted under another.
`first` and `second` are the two copies, exactly as the report wrote them: the path with
forward slashes, the first and last line counted from 1. `clone` is the verdict, true
when the two copies are duplicated code. `reason` says why in a few words. The two
copies name the record: a session started again leaves out the pairs already judged, and
each verdict is written as soon as it is given.

For each pair, the answer is `y` for duplicated code, `n` for code that only looks
alike, `s` to leave that pair for later, or `q` to stop; a verdict is followed by the
reason asked for. The copies are read from `--root`, the directory the report's paths
are relative to, which is the current one unless it is given.

Run it with `just label --report pairs.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, Final

from clonedigger.report import Span

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence
    from typing import TextIO

# The version of the JSON Lines format described above, carried by every record.
FORMAT_VERSION: Final = 1
# What the reader may answer, and what it does.
COMMANDS: Final = {
    "y": "duplicated code",
    "n": "not duplicated code",
    "s": "skip for now",
    "q": "stop here",
}
# A string, which argparse turns into a path: written with forward slashes, the help
# reads the same on every system.
DEFAULT_LABELS: Final = "benchmarks/labels.jsonl"
DEFAULT_WIDTH: Final = 60


@dataclass(frozen=True)
class Label:
    """The verdict on one reported pair.

    Attributes:
        first: One copy, as the report wrote it.
        second: The other.
        clone: True when the two copies are duplicated code.
        reason: Why, in a few words.
    """

    first: Span
    second: Span
    clone: bool
    reason: str

    @property
    def pair(self) -> tuple[Span, Span]:
        """Name the pair judged.

        Returns:
            Its two copies, which tell one record from another.
        """
        return (self.first, self.second)

    def record(self) -> str:
        """Write the label as one JSON Lines record.

        Returns:
            The record on one line, the version of the format first.
        """
        record = {"version": FORMAT_VERSION, **asdict(self)}
        # A reason is written by a reader and read by one: it keeps its own letters.
        return json.dumps(record, ensure_ascii=False)  # pragma: no mutate - None is as false


def _text(record: Mapping[str, object], key: str, where: str) -> str:
    """Read a string out of a record.

    Args:
        record: The record read.
        key: The name of the field.
        where: The file and line of the record, for the message.

    Returns:
        The field.

    Raises:
        TypeError: The field is missing, or is not a string.
    """
    value = record.get(key)
    if not isinstance(value, str):
        msg = f"{where}: {key} must be a string"
        raise TypeError(msg)
    return value


def _number(record: Mapping[str, object], key: str, where: str) -> int:
    """Read a whole number out of a record.

    Args:
        record: The record read.
        key: The name of the field.
        where: The file and line of the record, for the message.

    Returns:
        The field.

    Raises:
        TypeError: The field is missing, or is not a whole number.
    """
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{where}: {key} must be a whole number"
        raise TypeError(msg)
    return value


def _verdict(record: Mapping[str, object], key: str, where: str) -> bool:
    """Read a verdict out of a record.

    Args:
        record: The record read.
        key: The name of the field.
        where: The file and line of the record, for the message.

    Returns:
        The field.

    Raises:
        TypeError: The field is missing, or is not true or false.
    """
    value = record.get(key)
    if not isinstance(value, bool):
        msg = f"{where}: {key} must be true or false"
        raise TypeError(msg)
    return value


def _span(record: Mapping[str, object], key: str, where: str) -> Span:
    """Read one copy out of a record.

    Args:
        record: The record read.
        key: The name of the field, `first` or `second`.
        where: The file and line of the record, for the message.

    Returns:
        Where the copy lies.

    Raises:
        TypeError: The field is missing, or is not a copy with its path and its lines.
    """
    value = record.get(key)
    if not isinstance(value, dict):
        msg = f"{where}: {key} must hold path, start and end"
        raise TypeError(msg)
    inside = f"{where}: {key}"
    return Span(
        _text(value, "path", inside),
        _number(value, "start", inside),
        _number(value, "end", inside),
    )


def _object(line: str, where: str) -> Mapping[str, object]:
    """Read one line as a JSON object.

    Args:
        line: The line read.
        where: The file and line, for the message.

    Returns:
        The object.

    Raises:
        TypeError: The line is not a JSON object.
        ValueError: The line is not JSON at all.
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        msg = f"{where}: not JSON: {error}"
        raise ValueError(msg) from error
    if not isinstance(record, dict):
        msg = f"{where}: a record must be a JSON object"
        raise TypeError(msg)
    return record


def _label(line: str, where: str) -> Label:
    """Read one record of the verdicts.

    Args:
        line: The line read.
        where: The file and line, for the message.

    Returns:
        The verdict it records.

    Raises:
        ValueError: The record is of a version this format does not know.
    """
    record = _object(line, where)
    version = _number(record, "version", where)
    if version != FORMAT_VERSION:
        msg = f"{where}: version {version} is not the version read, {FORMAT_VERSION}"
        raise ValueError(msg)
    return Label(
        _span(record, "first", where),
        _span(record, "second", where),
        _verdict(record, "clone", where),
        _text(record, "reason", where),
    )


def read_labels(path: Path) -> list[Label]:
    """Read the verdicts given so far.

    Args:
        path: The JSON Lines file; it need not exist yet.

    Returns:
        One label per record, in the order of the file, blank lines left out; nothing
        at all when the file is not there.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")  # pragma: no mutate - "UTF-8" is the same
    return [
        _label(line, f"{path}:{number}")
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _pair(finding: object, where: str) -> tuple[Span, Span]:
    """Read the two copies of one finding of a report.

    Args:
        finding: The finding read.
        where: The report and the place of the finding, for the message.

    Returns:
        Its two copies.

    Raises:
        TypeError: The finding is not an object with its two copies.
    """
    if not isinstance(finding, dict):
        msg = f"{where}: a pair must be a JSON object"
        raise TypeError(msg)
    return (_span(finding, "first", where), _span(finding, "second", where))


def read_pairs(path: Path) -> list[tuple[Span, Span]]:
    """Read the pairs of a report written by `clonedigger --format json`.

    Args:
        path: The report.

    Returns:
        The two copies of each pair, in the order the report lists them.

    Raises:
        TypeError: The report is not a JSON array of pairs.
    """
    text = path.read_text(encoding="utf-8")  # pragma: no mutate - "UTF-8" is the same
    report = json.loads(text)
    if not isinstance(report, list):
        msg = f"{path}: a report must be a JSON array of pairs"
        raise TypeError(msg)
    return [
        _pair(finding, f"{path}: pair {number}") for number, finding in enumerate(report, start=1)
    ]


@dataclass(frozen=True)
class Session:
    """How the pairs are shown and the answers read.

    Attributes:
        root: The directory the paths of the report are relative to.
        width: The columns each copy is given.
        reader: Where the answers are read.
        writer: Where the pairs are shown.
    """

    root: Path
    width: int
    reader: TextIO
    writer: TextIO


def _fit(text: str, width: int) -> str:
    """Give a line exactly the width asked.

    Args:
        text: The line.
        width: The columns it is given.

    Returns:
        The line with its tabs expanded, padded with blanks and cut to the width.
    """
    return text.expandtabs(4).ljust(width)[:width]


def side_by_side(left: Sequence[str], right: Sequence[str], width: int) -> str:
    """Put two blocks of lines in two columns.

    Args:
        left: The lines of one copy.
        right: The lines of the other.
        width: The columns each column is given.

    Returns:
        The two blocks line by line, separated by a bar, the shorter one ending in
        blanks.
    """
    return "\n".join(
        f"{_fit(first, width)} | {_fit(second, width)}".rstrip()
        for first, second in zip_longest(left, right, fillvalue="")
    )


def copy_text(root: Path, span: Span) -> list[str]:
    """Read the lines of one copy, each with its number.

    Args:
        root: The directory the path of the copy is relative to.
        span: Where the copy lies.

    Returns:
        Its numbered lines; one line saying why instead, when the file cannot be read.
    """
    source = root / span.path
    try:
        text = source.read_text(encoding="utf-8")  # pragma: no mutate - "UTF-8" is the same
    except (OSError, UnicodeDecodeError) as error:
        return [f"<cannot read {span.path}: {error}>"]
    lines = text.splitlines()
    return [
        f"{number:>5} {text}"
        for number, text in enumerate(lines[span.start - 1 : span.end], start=span.start)
    ]


def _show(pair: tuple[Span, Span], heading: str, session: Session) -> None:
    """Show one pair, its two copies side by side.

    Args:
        pair: The two copies.
        heading: What to write above them, such as the place in the sample.
        session: Where to write, and how wide.
    """
    first, second = pair
    session.writer.write(f"\n{heading} {first}  ~  {second}\n")
    session.writer.write(
        side_by_side(copy_text(session.root, first), copy_text(session.root, second), session.width)
        + "\n"
    )


def _command(session: Session) -> str:
    """Ask for a verdict until one of the commands is answered.

    Args:
        session: Where to ask.

    Returns:
        The command answered; `q` at the end of the input.
    """
    prompt = ", ".join(f"{key} {what}" for key, what in COMMANDS.items())
    while True:
        session.writer.write(f"{prompt}? ")
        session.writer.flush()
        answer = session.reader.readline()
        if not answer:
            session.writer.write("\n")
            return "q"
        command = answer.strip().lower()
        if command in COMMANDS:
            return command


def _reason(session: Session) -> str:
    """Ask why the pair was judged so.

    Args:
        session: Where to ask.

    Returns:
        The answer, stripped; empty when nothing was typed.
    """
    session.writer.write("reason: ")
    session.writer.flush()
    return session.reader.readline().strip()


def judge(
    pairs: Sequence[tuple[Span, Span]], judged: Sequence[Label], session: Session
) -> Iterator[Label]:
    """Show each pair not judged yet and give its verdict.

    Args:
        pairs: The pairs of the report.
        judged: The verdicts already given, which are not asked again.
        session: Where the pairs are shown and the answers read.

    Yields:
        One label per verdict given, as soon as it is given; a skipped pair gives none,
        and `q` ends the run.
    """
    done = {label.pair for label in judged}
    todo = [pair for pair in pairs if pair not in done]
    for number, pair in enumerate(todo, start=1):
        _show(pair, f"[{number}/{len(todo)}]", session)
        command = _command(session)
        if command == "q":
            return
        if command == "s":
            continue
        yield Label(pair[0], pair[1], clone=command == "y", reason=_reason(session))


def _parser() -> argparse.ArgumentParser:
    """Describe the command line: the report, the verdicts, and how to show the copies.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="label",
        description="Judge each pair of a clonedigger JSON report and record the verdicts.",
    )
    parser.add_argument(
        "--report", type=Path, required=True, help="a report written by --format json"
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS,
        help="the JSON Lines file the verdicts are added to (default %(default)s)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(),
        help="the directory the paths of the report are relative to (default the current one)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help="columns each copy is given (default %(default)s)",
    )
    return parser


def _record(path: Path, labels: Iterable[Label]) -> int:
    """Record each verdict in the file as soon as it is given.

    Args:
        path: The JSON Lines file, which is added to, never rewritten.
        labels: The verdicts, as they are given.

    Returns:
        How many were recorded.
    """
    given = 0
    with path.open("a", encoding="utf-8") as sink:  # pragma: no mutate - "UTF-8" is the same
        for label in labels:
            sink.write(label.record() + "\n")
            sink.flush()
            given += 1
    return given


def main(argv: Sequence[str], reader: TextIO, writer: TextIO) -> None:
    """Run the tool: judge what is left of the report, and add the verdicts to the file.

    Args:
        argv: The arguments, without the program name.
        reader: Where the answers are read.
        writer: Where the pairs are shown.
    """
    options = _parser().parse_args(argv)
    pairs = read_pairs(options.report)
    judged = read_labels(options.labels)
    session = Session(options.root, options.width, reader, writer)
    # One file holds the verdicts of several reports: only this report's pairs are counted.
    wanted = set(pairs)
    already = sum(1 for label in judged if label.pair in wanted)
    given = _record(options.labels, judge(pairs, judged, session))
    writer.write(f"{already + given} of {len(pairs)} pairs judged, in {options.labels}\n")


if __name__ == "__main__":
    main(sys.argv[1:], sys.stdin, sys.stdout)
