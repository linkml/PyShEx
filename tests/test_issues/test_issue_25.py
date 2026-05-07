import os
import pytest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from pyshex.shex_evaluator import evaluate_cli


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
VALIDATION_DIR = os.path.join(DATA_DIR, 'validation')
RDF_FILE = os.path.join(VALIDATION_DIR, 'simple.ttl')
SHEX_FILE = os.path.join(VALIDATION_DIR, 'simple.shex')


def test_nostart() -> None:
    outf = StringIO()
    with redirect_stdout(outf):
        evaluate_cli(f"{RDF_FILE} {SHEX_FILE} -A".split())
    assert outf.getvalue().strip() == """\
Errors:
  Focus: None
  Start: None
  Reason: START node is not specified"""


def test_all_nodes_without_focus_errors_to_stderr() -> None:
    errf = StringIO()
    with redirect_stderr(errf):
        evaluate_cli(f"{RDF_FILE} {SHEX_FILE} -s http://example.org/shapes/S".split())
    assert errf.getvalue().strip() == (
        'Error: You must specify one or more graph focus nodes, '
        'supply a SPARQL query, or use the "-A" option'
    )


def test_all_nodes_with_shape_reports_failures() -> None:
    outf = StringIO()
    with redirect_stdout(outf):
        evaluate_cli(f"{RDF_FILE} {SHEX_FILE} -A -s http://example.org/shapes/S".split())
    assert outf.getvalue().strip() == """\
Errors:
  Focus: http://a.example/s1
  Start: http://example.org/shapes/S
  Reason:   Testing :s1 against shape http://example.org/shapes/S
       No matching triples found for predicate :s4

  Focus: http://a.example/s2
  Start: http://example.org/shapes/S
  Reason:   Testing :s2 against shape http://example.org/shapes/S
       No matching triples found for predicate :s4

  Focus: http://a.example/s3
  Start: http://example.org/shapes/S
  Reason:   Testing :s3 against shape http://example.org/shapes/S
       No matching triples found for predicate :s4"""