import os
from pyshex.shex_evaluator import evaluate_cli


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
VALIDATION_DIR = os.path.join(DATA_DIR, 'validation')
RDF_FILE = os.path.join(VALIDATION_DIR, 'anon_start.ttl')
SHEX_FILE = os.path.join(VALIDATION_DIR, 'anon_start.shex')


def test_anon_start() -> None:
    assert evaluate_cli(f"{RDF_FILE} {SHEX_FILE} -A") == 0