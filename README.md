# Clone Digger, revived for Python 3

[![CI](https://github.com/mathbeal/clonedigger-revival/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/mathbeal/clonedigger-revival/actions/workflows/quality.yml)
[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![Licence: GPL-3.0-or-later](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue)](LICENSE)
[![REUSE compliant](https://img.shields.io/badge/REUSE-compliant-green)](https://reuse.software)
[![Coverage: 100 % of lines and branches](https://img.shields.io/badge/coverage-100%25%20lines%20%26%20branches-brightgreen)](justfile)
[![Mutation testing: every mutant caught](https://img.shields.io/badge/mutants-all%20caught-brightgreen)](.github/workflows/mutation.yml)
[![Types: mypy strict](https://img.shields.io/badge/types-mypy%20strict-blue)](https://mypy.readthedocs.io)
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

Measured on 2026-10-08, with default settings and copies of at least 5 lines for
jscpd 4.0.5 (`--format python --min-lines 5`) and pylint's `duplicate-code` (4 lines):

| Code | Clone Digger | pylint `duplicate-code` | jscpd |
|---|---|---|---|
| `asyncio` of Python 3.14 (15,000 lines) | 174 clones | 31 | 3 |
| avenir-mcp 0.5 (10,500 lines) | 27 | 0 | 1 |

The counts are pairs: three copies of one block make three. Sampled by hand, Clone
Digger's are real copies with renamed names, such as `sock_recv_into` and
`sock_recvfrom` in `asyncio/selector_events.py`; precision over every pair has not been
measured. The tools see different things: the one copy jscpd finds in avenir-mcp lies
inside a large dictionary literal whose surrounding statements differ, which a tool that
compares whole statements does not report. Run them together.

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
just golden    # record the original's answers again (needs Docker)
```

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
