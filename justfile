# The repository lives in iCloud Drive, which hides the .pth files of a local .venv,
# and Python 3.14 skips hidden .pth files: the virtual environment lives outside.
export UV_PROJECT_ENVIRONMENT := env("UV_PROJECT_ENVIRONMENT", home_directory() / ".local/share/clonedigger-dev/venv")

# Lint, types and tests: what must pass before every commit.
check: lint types test

lint:
    uv run ruff format --check src tests
    uv run ruff check src tests

types:
    uv run mypy

test:
    uv run pytest

# Reformat.
fix:
    uv run ruff check --fix src tests
    uv run ruff format src tests

# Record again what the original 1.1.0 answers (needs Docker).
golden:
    docker run --rm -v "$PWD":/w -w /w python:2.7-slim python tests/golden/au_cases_py2.py > tests/golden/anti_unification.json
    docker run --rm -v "$PWD":/w -w /w python:2.7-slim python tests/golden/suffix_tree_cases_py2.py > tests/golden/suffix_tree.json
