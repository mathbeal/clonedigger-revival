# An example, and the four reports on it

[`shipping.py`](shipping.py) is a small module of a parcel service, written the way a
hurried week leaves code: two cost functions and two readers of the carrier's file, each
pair the same code with other names. Nothing imports it; it is here to be read.

Run on it with its default options, Clone Digger finds two clones, each at a distance of
4, and exits with the status 1 because it found some:

```
$ clonedigger examples/shipping.py
examples/shipping.py:46-54  ~  examples/shipping.py:35-43  (distance 4)
examples/shipping.py:66-72  ~  examples/shipping.py:57-63  (distance 4)
2 clones found.
```

That same run, written out in each of the four formats:

| File | Format | What it is for |
|---|---|---|
| [`report.txt`](report.txt) | `--format text` | a line per clone, for a reader |
| [`report.json`](report.json) | `--format json` | the two copies and the distance of each clone, for a program |
| [`report.sarif`](report.sarif) | `--format sarif` | a SARIF 2.1.0 log, read by code scanning: each clone on its first copy, the second as a related location |
| [`report.html`](report.html) | `--format html` | one page to save and open: the two copies side by side, with the words that differ marked |

`report.html` is the one to open first: it shows that `amount`, `cost` and
`STANDARD_RATE` on one side answer `total`, `price` and `EXPRESS_RATE` on the other,
and that the rest of the two functions is the same code. A tool comparing lines or
tokens sees two different blocks.

Both clones span a whole function, its `def` line included: the statements of the module
are compared as well as those of each body, and a function definition is one of them,
with everything written under it.

## The workflow beside them

[`code-scanning.yml`](code-scanning.yml) is a GitHub Actions workflow to copy into a
project: it runs the tool, writes `report.sarif` of the kind above and sends it to
GitHub code scanning, where each clone becomes an alert. What each of its lines is for
is in [docs/github-code-scanning.md](../docs/github-code-scanning.md).

## Keeping them up to date

    just examples

writes the four files again from `shipping.py`. `tests/test_examples.py` runs the same
command in each format and fails unless every committed report matches it byte for byte,
so a change of what the tool writes is noticed here as well. The SARIF and HTML reports
carry the version of the tool, so they are written again when it changes.

Everything in this directory is under the licence of the repository, GPL-3.0-or-later.
