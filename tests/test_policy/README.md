# Repository policy tests

These tests enforce the maintenance constraints LinkML asked for:

1. PyPI releases must not break compatibility (see `tests/test_contract`).
2. PyShEx should keep up with current Python releases (`test_python_support.py`).
3. No unexpected heavyweight dependencies (`test_dependencies.py`).

They read `pyproject.toml`, `uv.lock` and the CI workflow, so they only run from a
source checkout. They need `tomllib`, so they skip on Python 3.10; pre-commit and
the CI `policy` job run them on a current Python.

Adding a dependency, or accepting a new transitive one, is allowed. It just has to be
a deliberate, reviewed edit to the allowlist in `test_dependencies.py`.

A runtime dependency may temporarily come from a git or path source (`[tool.uv.sources]`)
if it is listed in `ALLOWED_NON_PYPI_SOURCES`. The release workflow runs these tests with
`PYSHEX_RELEASE_CHECK=1`, which allows none, because published wheels always resolve
dependencies from PyPI.
