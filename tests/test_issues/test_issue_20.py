import os
import pytest
from contextlib import redirect_stdout
from io import StringIO

from pyshex import PrefixLibrary
from pyshex.shex_evaluator import evaluate_cli


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))


@pytest.fixture
def paths() -> dict[str, str]:
    return {
        "shex":     os.path.join(DATA_DIR, 'issue_20.shex'),
        "rdf":      os.path.join(DATA_DIR, 'issue_20.ttl'),
        "expected": os.path.join(DATA_DIR, 'issue_20.errors'),
    }


def test_max_cardinality_zero_and_error_reporting(paths: dict[str, str]) -> None:
    """Test max cardinality of 0 AND error reporting."""
    pl = PrefixLibrary(paths["rdf"])

    output = StringIO()
    with redirect_stdout(output):
        evaluate_cli(f"{paths['rdf']} {paths['shex']} -fn {pl.EX.BPM1}")
        evaluate_cli(f"{paths['rdf']} {paths['shex']} -fn {pl.EX.BPM2}")

    actual = output.getvalue()

    if not os.path.exists(paths["expected"]):
        with open(paths["expected"], 'w') as f:
            f.write(actual)
        pytest.fail("Expected output file created — rerun the test suite")

    with open(paths["expected"]) as f:
        expected = f.read()

    assert actual == expected