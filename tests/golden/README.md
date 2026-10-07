# Reference results of the original Clone Digger

Everything here was produced by the **unmodified Clone Digger 1.1.0** (first commit
of this repository), run under Python 2.7 in the `python:2.7-slim` Docker image on
2026-10-07. The Python 3 port must give the same answers on the same inputs; any
difference is either a bug in the port or a deliberate change, documented as such.

- `anti_unification.json`: six anti-unification cases, made by `au_cases_py2.py`.
- `inputs/`: two small files with one clone whose variables were renamed.
- `cpd_default.xml`, `run_default.log`: the clone report and the console output of
  `clonedigger.py --cpd-output` on those inputs, with default thresholds.

To reproduce:

    docker run --rm -v "$PWD":/w -w /w python:2.7-slim python tests/golden/au_cases_py2.py
    docker run --rm -v "$PWD":/w -w /w/clonedigger python:2.7-slim \
      python clonedigger.py --cpd-output -o /tmp/out.xml \
      /w/tests/golden/inputs/prices.py /w/tests/golden/inputs/report.py
