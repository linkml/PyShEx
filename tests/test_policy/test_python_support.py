"""Keep supported Python versions consistent everywhere and current with CPython releases."""
import datetime
import json
import os
import re
import urllib.request

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from tests.test_policy._repo import TEST_WORKFLOW, pyproject

CLASSIFIER = re.compile(r"^Programming Language :: Python :: (3\.\d+)$")


def classifier_versions() -> list[str]:
    found = [m.group(1) for c in pyproject()["project"]["classifiers"] if (m := CLASSIFIER.match(c))]
    return sorted(found, key=Version)


def ci_matrix_versions() -> list[str]:
    text = TEST_WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"^\s*python-version:\s*\[([^\]]*)\]", text, re.MULTILINE)
    assert m, f"no python-version matrix in {TEST_WORKFLOW}"
    return sorted((v.strip().strip("\"'") for v in m.group(1).split(",")), key=Version)


def test_classifiers_match_ci_matrix():
    assert classifier_versions() == ci_matrix_versions(), (
        "Every advertised Python version must be tested in CI, and vice versa"
    )


def test_requires_python_floor_matches_oldest_classifier():
    spec = SpecifierSet(pyproject()["project"]["requires-python"])
    oldest = classifier_versions()[0]
    assert Version(oldest) in spec
    below = f"3.{Version(oldest).minor - 1}"
    assert Version(below) not in spec, f"requires-python admits {below}, which is neither advertised nor tested"


def test_requires_python_has_no_upper_cap():
    """Caps like <3.14 stop LinkML users from installing on a new Python even when it works."""
    spec = SpecifierSet(pyproject()["project"]["requires-python"])
    assert not [s for s in spec if s.operator in {"<", "<=", "==", "~="}]


def test_versions_are_contiguous():
    minors = [Version(v).minor for v in classifier_versions()]
    assert minors == list(range(minors[0], minors[-1] + 1)), "gaps in supported Python versions"


def test_tooling_targets_match():
    project = pyproject()
    wanted = {f"py3{Version(v).minor}" for v in classifier_versions()}
    black = set(project.get("tool", {}).get("black", {}).get("target-version", []))
    assert not black or black == wanted, "tool.black.target-version out of sync with classifiers"
    envs = project.get("tool", {}).get("tox", {}).get("env_list", [])
    tox = {f"py3{v}" for e in envs for v in re.findall(r"3(1\d)", e)}
    assert not tox or tox == {f"py3{Version(v).minor}" for v in classifier_versions()}, (
        "tool.tox.env_list out of sync with classifiers"
    )


# How long after a CPython release PyShEx may go without supporting it.
# Dependencies with compiled extensions often need a few weeks to publish wheels.
NEW_PYTHON_GRACE = datetime.timedelta(days=90)


def network_disabled() -> bool:
    """Same convention as tests/__init__.py: SKIP_EXTERNAL_URLS=false/0/no/empty means enabled."""
    return os.environ.get("SKIP_EXTERNAL_URLS", "").lower() not in ("", "0", "false", "no")


@pytest.mark.skipif(network_disabled(), reason="network disabled")
def test_newest_cpython_release_is_supported():
    """Every stable CPython (per endoflife.date) released more than NEW_PYTHON_GRACE ago must be supported."""
    try:
        with urllib.request.urlopen("https://endoflife.date/api/python.json", timeout=10) as resp:
            cycles = json.load(resp)
    except Exception as e:  # offline, rate limited, ...
        pytest.skip(f"could not reach endoflife.date: {e}")
    cutoff = (datetime.date.today() - NEW_PYTHON_GRACE).isoformat()
    released = [c["cycle"] for c in cycles if c.get("releaseDate", "9999") <= cutoff and c["cycle"].startswith("3.")]
    newest = max(released, key=Version)
    assert Version(classifier_versions()[-1]) >= Version(newest), (
        f"Python {newest} has been out for more than {NEW_PYTHON_GRACE.days} days; add it to the classifiers "
        "and the CI matrix"
    )
