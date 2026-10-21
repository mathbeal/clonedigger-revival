# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

# The repository lives in iCloud Drive, which hides the .pth files of a local .venv,
# and Python 3.14 skips hidden .pth files: the virtual environment lives outside.
export UV_PROJECT_ENVIRONMENT := env("UV_PROJECT_ENVIRONMENT", home_directory() / ".local/share/clonedigger-dev/venv")

# Run `just` to see the recipes.
default:
    @just --list

# Install the project and its development tools.
setup:
    uv sync

# Every gate, in the order CI will run them.
check: lint types test deadcode vocabulary lock

# Format, lint (ruff, pylint), Google docstrings complete (pydoclint), dependencies
# declared and used (deptry).
lint:
    uv run ruff format --check src tests benchmarks vulture_whitelist.py
    uv run ruff check src tests benchmarks vulture_whitelist.py
    uv run pylint src tests benchmarks
    uvx pydoclint==0.10.1 src benchmarks
    uvx pydoclint==0.10.1 --skip-checking-short-docstrings=True --exclude 'golden|samples' tests
    uv run deptry src

types:
    uv run mypy

# Tests at 100 % of lines and branches.
test:
    uv run pytest

# Code that nothing calls.
deadcode:
    uv run vulture

# One word per idea.
vocabulary:
    uvx lexdrift check src

lock:
    uv lock --check

# Where the code is hardest to maintain: functions of complexity C or worse, then the
# Maintainability Index of each file, lowest first. A report to follow over time, not a
# gate: radon's grade A starts at 20.
complexity:
    uvx radon==6.0.1 cc -s -n C src
    uvx radon==6.0.1 mi -s src | sort -t'(' -k2 -n

# Typos, the workflows, and the copyright and licence of every file (REUSE).
hygiene:
    uvx typos .
    uvx --from 'reuse[charset-normalizer]==6.2.0' reuse lint
    uvx zizmor --persona=regular .github/workflows/
    # The workflow of docs/github-code-scanning.md is written to be copied into another
    # project: it is held to the strictest persona zizmor has.
    uvx zizmor --persona=auditor examples/code-scanning.yml

# Check that every link of the Markdown files leads somewhere (needs Docker).
links:
    docker run --rm -v "$PWD:/input" -w /input lycheeverse/lychee@sha256:eaff3e0a13603c9a701accfcc84f44158bb77bf36ecfa4622b626056c3463892 --config lychee.toml --no-progress README.md CONTRIBUTING.md SECURITY.md ROADMAP.md NOTICE.md CODE_OF_CONDUCT.md docs/precision.md docs/github-code-scanning.md examples/README.md

# Write CHANGELOG.md again from the commit history (git-cliff, cliff.toml).
changelog:
    uvx git-cliff -o CHANGELOG.md

# For pre-commit: ruff on the files it names, from the lockfile and the venv above.
[private]
ruff-hook *files:
    uv run ruff check --fix --force-exclude {{files}}
    uv run ruff format --force-exclude {{files}}

# Compare Clone Digger, pylint duplicate-code and jscpd on pinned releases of well-known
# projects: time, memory and clones (needs Node.js). Names restrict it to those projects.
compare *projects:
    uv run python benchmarks/compare.py {{projects}}

# Judge the pairs of a report written by `clonedigger --format json`, each one shown side
# by side, and add the verdicts to benchmarks/labels.jsonl: the sample precision is
# measured on. A run stopped with `q` picks up where it left off.
# Example: just label --report pairs.json --root ~/code/project
label *options:
    uv run python benchmarks/label.py {{options}}

# Draw again the sample of pairs that precision is measured on: the detection run on two
# of the projects above, and the same number of their pairs drawn with a fixed seed
# (docs/precision.md). It writes benchmarks/sample.json, which must come out unchanged.
sample:
    uv run python -m benchmarks.sample

# Precision: the share of the pairs drawn that a reader judged duplicated code, with its
# Wilson 95 % interval, from the two files committed, benchmarks/sample.json and
# benchmarks/labels.jsonl. The figures of docs/precision.md and of the README.
precision:
    uv run python -m benchmarks.precision

# Write the four reports of examples/ again, from the example file beside them. The
# command answers 1 because that file holds clones, which is why it is there; any other
# status stops the recipe. tests/test_examples.py checks that the reports are up to date.
examples:
    #!/usr/bin/env bash
    set -euo pipefail
    for pair in text:txt json:json sarif:sarif html:html; do
      uv run clonedigger examples/shipping.py --format "${pair%:*}" \
        > "examples/report.${pair#*:}" || [ "$?" -eq 1 ]
    done

# Mutation testing: slow; run before a release, and read what survives.
mutate:
    uv run mutmut run
    uv run mutmut results

# Every Hypothesis property with EXAMPLES examples instead of 100.
fuzz examples="50000":
    CLONEDIGGER_FUZZ_EXAMPLES={{examples}} uv run pytest -o addopts="" -p no:cacheprovider -q --hypothesis-profile=fuzz

# Time the detection on packages of the standard library of growing size, and on the
# whole of it (tests left out). Reference, Apple M4, Python 3.14: json 0.09 s, email
# 0.3 s, asyncio 0.5 s, the whole library (455,000 lines) 50 s and 1.1 GB.
bench:
    #!/usr/bin/env bash
    set -euo pipefail
    lib="$(uv run python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
    for target in json email asyncio .; do
      start=$(date +%s.%N)
      found="$(uv run clonedigger "$lib/$target" --ignore-dir test --ignore-dir tests --ignore-dir idlelib | tail -1)" || true
      echo "$target: $(echo "$(date +%s.%N) - $start" | bc) s, $found"
    done

# Known vulnerabilities in the locked dependencies.
audit:
    uv export --frozen --no-emit-project --all-groups -o /tmp/clonedigger-req.txt
    uvx pip-audit --strict --disable-pip -r /tmp/clonedigger-req.txt

# Build the wheel and the sdist, dated by the last commit, and check them.
build:
    rm -rf dist
    SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" uv build
    uv run --no-project --with twine twine check --strict dist/*

# Build twice, the second time with every source file touched, and fail unless the wheel
# and the sdist are the same bit for bit.
reproducible:
    #!/usr/bin/env bash
    set -euo pipefail
    out="$(mktemp -d)"
    export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
    uv build -q -o "$out/first"
    touch src/clonedigger/*.py
    uv build -q -o "$out/second"
    (cd "$out/first" && shasum -a 256 -- *) > "$out/first.sha256"
    (cd "$out/second" && shasum -a 256 --check --strict ../first.sha256)

# Reformat.
fix:
    uv run ruff check --fix src tests benchmarks vulture_whitelist.py
    uv run ruff format src tests benchmarks vulture_whitelist.py

# Record again what the original 1.1.0 answers (needs Docker).
golden:
    docker run --rm -v "$PWD":/w -w /w python:2.7-slim python tests/golden/au_cases_py2.py > tests/golden/anti_unification.json
    docker run --rm -v "$PWD":/w -w /w python:2.7-slim python tests/golden/suffix_tree_cases_py2.py > tests/golden/suffix_tree.json
    for name in bottle six docopt; do \
      docker run --rm -v "$PWD":/w -w /w/legacy/clonedigger python:2.7-slim python clonedigger.py --cpd-output -o /w/tests/golden/corpus/$name.cpd.xml /w/tests/golden/corpus/$name.py > /dev/null; \
      sed -i.bak 's#/w/tests/golden/corpus/#corpus/#g' tests/golden/corpus/$name.cpd.xml && rm tests/golden/corpus/$name.cpd.xml.bak; \
    done
