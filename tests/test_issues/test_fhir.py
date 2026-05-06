import os
from contextlib import redirect_stdout
from io import StringIO

import pytest

from pyshex.shex_evaluator import evaluate_cli

SOURCE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


def _run_and_compare(args, result_path):
    outf = StringIO()
    with redirect_stdout(outf):
        evaluate_cli(args)

    if not os.path.exists(result_path):
        with open(result_path, 'w') as f:
            f.write(outf.getvalue())
        pytest.fail(f"Created {result_path} -- rerun")

    with open(result_path) as f:
        assert f.read() == outf.getvalue()


def test_observation_online():
    """Test online FHIR example."""
    _run_and_compare(
        "http://hl7.org/fhir/observation-example-haplotype2.ttl "
        "http://build.fhir.org/observation.shex "
        "-fn http://hl7.org/fhir/Observation/example-haplotype2",
        os.path.join(SOURCE_DIR, 'example-haplotype2_online.results'),
    )


def test_observation():
    """Test of local FHIR example."""
    rdf = os.path.join(SOURCE_DIR, 'example-haplotype2.ttl')
    shex = os.path.join(SOURCE_DIR, 'observation.shex')
    _run_and_compare(
        f"{rdf} {shex} -fn http://hl7.org/fhir/Observation/example-haplotype2",
        os.path.join(SOURCE_DIR, 'example-haplotype2.results'),
    )