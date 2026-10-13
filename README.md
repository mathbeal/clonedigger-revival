# Clone Digger, revived for Python 3

[![CI](https://github.com/mathbeal/clonedigger-revival/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/mathbeal/clonedigger-revival/actions/workflows/quality.yml)
[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![Licence: GPL-3.0-or-later](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue)](LICENSE)
[![REUSE compliant](https://img.shields.io/badge/REUSE-compliant-green)](https://reuse.software)
[![Coverage: 100 % of lines and branches](https://img.shields.io/badge/coverage-100%25%20lines%20%26%20branches-brightgreen)](justfile)
[![Mutation testing: every mutant caught](https://img.shields.io/badge/mutants-all%20caught-brightgreen)](.github/workflows/mutation.yml)
[![Types: mypy strict](https://img.shields.io/badge/types-mypy%20strict-blue)](https://mypy.readthedocs.io)
[![Vocabulary: lexdrift](https://img.shields.io/badge/vocabulary-lexdrift-blue)](https://github.com/mathbeal/lexdrift)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Clone Digger is the work of Peter Bulychev.** It finds duplicated code by comparing
the shape of syntax trees and measuring their differences with *anti-unification*, an
algorithm he designed with Marius Minea. It was written in 2008 during the Google
Summer of Code and last released, as version 1.1.0, in February 2010:
<http://clonedigger.sourceforge.net>.

That release runs on Python 2 only: it is built on the `compiler` module, which
Python 3.0 removed. This repository brings the same tool to current Python. It is an
update, not a new tool: same algorithm, same thresholds, same licence, credited to its
authors, and held to the answers of the original by its tests.

> Not released on PyPI yet. The name `clonedigger` there belongs to the original
> project, and is not used without its author's agreement.

## Why another duplicate finder

Most tools compare lines or tokens: they find copies, and miss them as soon as names
are changed. Clone Digger compares syntax trees. Two blocks that do the same work with
other variable names, other constants or a slightly different expression have the same
shape, and anti-unification measures how far apart they are: how many names, constants
or subtrees one would have to change to turn one into the other.

```
$ clonedigger tests/golden/inputs
tests/golden/inputs/prices.py:13-18  ~  tests/golden/inputs/prices.py:2-7  (distance 4)
1 clone found.
```

Those two loops compute a total with `total`, `item` and `price` on one side, `amount`,
`line` and `cost` on the other: a line-based tool sees nothing in common.

## Install

From a clone of this repository, with [uv](https://docs.astral.sh/uv/):

```
uv tool install .
```

Python 3.12 or later. The tool has no dependency.

## Use

```
clonedigger PATH [PATH ...] [--format text|json|sarif|html] [options]
```

`PATH` is a Python file or a directory, searched recursively. The exit status is 0 when
no clone is found, 1 when clones are found, 2 when a file cannot be read, so that the
command can gate a CI job.

| Option | Default | Meaning |
|---|---|---|
| `--format` | `text` | `text` for a reader, `json` for a program, `sarif` for code scanning, `html` for one page to open |
| `--size-threshold` | 5 | fewest lines a clone spans, on both sides |
| `--distance-threshold` | 5 | largest difference between the two copies; -1 keeps every candidate |
| `--clustering-threshold` | 10 | largest cost of gathering two statements under one pattern |
| `--hashing-depth` | 1 | how deep statements are hashed into buckets; deeper is faster and may miss clones |
| `--force` | off | keep long runs of similar statements (lists of assignments), left out by default |
| `--func-prefixes` | none | comma-separated prefixes of function names to leave out, such as `test_` |
| `--ignore-dir` | none | a directory name to skip, repeatable |
| `--version` | | print the version and exit |

The HTML report shows each clone side by side, statement against statement, with the
words that differ marked. The SARIF report locates each clone on its first copy, with the
second as a related location, which GitHub code scanning displays.

The Python running `clonedigger` reads the syntax of its own version and earlier:
`match`, `async`, `yield from`, `except*`, generics, f-strings and the rest are read
(see `tests/samples/syntax_probe.py`). Code written for a later Python must be read with
that Python; Python 2 code is not read.

## How it works

1. Each file is parsed with `ast` and split into sequences of statements: the bodies of
   modules, functions, classes, branches and loops.
2. Statements of the same rough shape fall in the same bucket. In each bucket they are
   gathered into clusters around a common pattern, the anti-unifier of their members:
   the most specific tree they all fit, with holes where they differ.
3. Each statement is labelled with its cluster, so a sequence becomes a string of labels.
4. A suffix tree finds the longest runs of labels that occur in two places.
5. Each candidate pair is anti-unified: it is a clone when the two sides differ by less
   than the distance threshold. A clone lying inside a larger one is dropped.

Imports, docstrings, type annotations of signatures and type parameters are left out of
the comparison: two functions that do the same work with other annotations are still
clones.

## Faithful, and where it differs

The tests run the unmodified 1.1.0 release under Python 2.7 (Docker) and record its
answers: anti-unification cases, suffix tree cases, and the clones it finds in three real
files that both versions read (bottle, six, docopt). The port gives the same answers.

It differs on purpose, each time with a test:

- after a clone is cut out of a candidate, 1.1.0 searched the part before it minus its
  last statement, and could lose a clone there; the whole part is searched;
- 1.1.0 gave a statement to every cluster that improved on the best so far, which made
  the first clusters look larger than they were; only the closest one receives it;
- the HTML report marks differences word by word instead of character by character;
- 1.1.0 announced that sequences over 1,000 statements were left out, and did not leave
  them out; the port neither announces nor does it.

The front ends for Java, JavaScript and Lua and the Eclipse plugin of 1.1.0 are not
ported. The original release is kept unmodified under `legacy/`.

## Compared with line and token tools

[pylint](https://pylint.readthedocs.io)'s `duplicate-code` check compares lines, and
[jscpd](https://github.com/kucherenko/jscpd) compares tokens, in any language: both
find copies, and miss them once names change. Clone Digger compares syntax trees.

Measured on 2026-10-08 by `just compare`, which downloads each release from PyPI, checks
its SHA-256 and runs the three tools on its package, tests left out, with copies of at
least 5 lines: Clone Digger 0.0.1.dev0 (defaults), pylint 4.0.9
(`--disable=all --enable=duplicate-code --min-similarity-lines=5`) and jscpd 4.0.5
(`--format python --min-lines 5`), on an Apple M4 (24 GB) with Python 3.14.7. The raw
figures are in [benchmarks/results.json](benchmarks/results.json).

Clones found, as pairs, and the share of the lines that lie in at least one copy:

| Project | Lines | Clone Digger | pylint `duplicate-code` | jscpd |
|---|--:|--:|--:|--:|
| requests 2.34.2 | 6,385 | 17 (3.7 %) | 0 (0.0 %) | 3 (1.3 %) |
| httpx 0.28.1 | 8,828 | 82 (19.8 %) | 18 (1.9 %) | 11 (3.8 %) |
| Flask 3.1.3 | 9,199 | 49 (9.8 %) | 1 (1.5 %) | 2 (0.4 %) |
| click 8.5.0 | 12,674 | 90 (6.6 %) | 1 (0.3 %) | 1 (0.2 %) |
| FastAPI 0.142.4 | 22,171 | 134 (43.4 %) | 42 (26.0 %) | 23 (4.7 %) |
| FastMCP 4.0.11 | 80,586 | 987 (11.1 %) | 86 (2.6 %) | 137 (4.8 %) |
| rich 15.0.0 | 38,515 | 121 (6.0 %) | 478 (29.6 %) | 176 (32.3 %) |
| SQLAlchemy 2.1.4 | 252,707 | 5,341 (12.8 %) | 69 (1.0 %) | 83 (0.9 %) |
| Django 6.1.2 | 165,376 | 5,166 (10.3 %) | 198 (1.8 %) | 84 (1.6 %) |

Time and largest memory held:

| Project | Clone Digger | pylint `duplicate-code` | jscpd |
|---|--:|--:|--:|
| requests 2.34.2 | 0.2 s, 46 MB | 1.1 s, 98 MB | 0.5 s, 123 MB |
| httpx 0.28.1 | 0.2 s, 51 MB | 1.4 s, 116 MB | 0.3 s, 128 MB |
| Flask 3.1.3 | 0.2 s, 46 MB | 1.6 s, 130 MB | 0.3 s, 127 MB |
| click 8.5.0 | 0.3 s, 63 MB | 2.1 s, 143 MB | 0.4 s, 135 MB |
| FastAPI 0.142.4 | 0.4 s, 71 MB | 2.3 s, 140 MB | 0.4 s, 173 MB |
| FastMCP 4.0.11 | 2.7 s, 176 MB | 13.9 s, 237 MB | 2.5 s, 328 MB |
| rich 15.0.0 | 1.0 s, 115 MB | 6.2 s, 156 MB | 1.2 s, 227 MB |
| SQLAlchemy 2.1.4 | 15.3 s, 526 MB | 50.1 s, 491 MB | 2.1 s, 369 MB |
| Django 6.1.2 | 17.2 s, 448 MB | 102.1 s, 428 MB | 4.1 s, 543 MB |

Times vary by about a quarter from one run to the next on a desktop machine; the
clones do not vary.

How to read them:

- **Pairs grow fast with families of copies**: n copies of one block make n(n-1)/2
  pairs. Most of Django's pairs come from `conf/locale`, a hundred `formats.py` files
  that differ only in their values; most of SQLAlchemy's from the proxies of
  `ext/asyncio` and its bundled test suite. The share of lines is the fairer measure.
- **What Clone Digger adds** are copies whose names differ: in httpx, the methods of
  `Client` and `AsyncClient`; in Flask, the shortcuts `get`, `post`, `delete` and the
  like, each the same code with another verb.
- **FastAPI writes its eight HTTP methods twice**, in `APIRouter` and in `FastAPI`, and
  each one is some 380 lines, most of them a signature documented parameter by
  parameter: `get` and `put` against `put` and `post` make one clone of 760 lines, at
  a distance of 4. pylint sees part of it, jscpd little. In FastMCP the copies are spread out: settings
  declared on one pattern, and twin methods such as `_get_resource` and
  `_get_resource_template`.
- **What it does not see** is a copy inside one statement. In rich, 30 % of the lines
  are tables of Unicode widths, one large literal per version of Unicode: pylint and
  jscpd report them, Clone Digger compares statements and does not.
- **Some pairs overlap**: in a run of similar statements, a window and the same window
  shifted by two statements can be reported as a pair, as 1.1.0 did.
- **Precision is not measured yet.** Pairs sampled by hand are real copies. `just label`
  shows the two copies of each reported pair side by side and writes the verdict down,
  one JSON Lines record per pair; the labelled sample to measure precision on is still
  to come ([roadmap](ROADMAP.md)).

Run them together: they see different things.

## Speed and memory

On an Apple M4 with Python 3.14: the `json` package of the standard library takes
0.09 s, `email` 0.3 s, `asyncio` 0.5 s, and the whole standard library (455,000 lines,
tests left out) 50 s and 1.1 GB of memory, against 222 s and 2.6 GB at first, with the
same 9,579 clones. What was done, measured step by step:

- clustering, marking and refinement weigh only what they need (the sizes and the
  distance of an anti-unification, not its pattern), and stop as soon as the answer
  cannot change;
- marking starts from the cluster a statement was gathered into, which bounds the rest;
- the suffix tree keeps where each suffix starts instead of a copy of it, and hands its
  two million candidates over one at a time instead of in one list;
- trees no longer keep their covered lines on every node, and share line sets and names;
- a candidate is shrunk to its clone without trying every length at every start, which
  took a time growing with the cube of its length: with `--force`, two files of 800
  similar assignments took more than four minutes, and take about 20 s. The clones are the
  same, and a test checks it against the search of 1.1.0; ordinary code takes a little
  longer (50 s on the standard library, against 47 s), the price of that bound.

The rest of the time goes to the largest bucket of similar statements (4,668 in the
standard library), compared cluster by cluster, and to the suffix tree. `just bench`
measures it again.

## Development

```
just check     # lint, types, tests at 100 % of lines and branches, dead code, vocabulary, lockfile
just hygiene   # typos and licences (REUSE)
just mutate    # mutation testing: every mutant must be caught
just compare   # Clone Digger, pylint and jscpd on pinned releases (needs Node.js)
just label     # judge the pairs of a JSON report, side by side, and record the verdicts
just golden    # record the original's answers again (needs Docker)
```

Vocabulary kept consistent by [lexdrift](https://github.com/mathbeal/lexdrift)
([PyPI](https://pypi.org/project/lexdrift/)): one word per idea in `src`.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).

## Citing

If you use or study this tool, please cite the original work
([CITATION.cff](CITATION.cff)):

- Peter Bulychev and Marius Minea. *Duplicate Code Detection Using
  Anti-Unification.* Proceedings of the Spring/Summer Young Researchers' Colloquium
  on Software Engineering (SYRCoSE), 2008. doi:10.15514/SYRCOSE-2008-2-22
- Peter Bulychev, Egor Kostylev and Vladimir Zakharov. *Anti-unification Algorithms
  and Their Applications in Program Analysis.* Perspectives of Systems Informatics,
  Lecture Notes in Computer Science, Springer, 2010, pp. 413-423.
  doi:10.1007/978-3-642-11486-1_35

## Licence

GNU General Public License, version 3 or (at your option) any later version, as the
original: see [LICENSE](LICENSE). Files taken from Clone Digger keep their original
copyright notice; files that are modified say so, with the date. Every file states its
copyright and licence ([REUSE](https://reuse.software)); [NOTICE.md](NOTICE.md) gives the
provenance of each part.
