import os
import pytest
from contextlib import redirect_stdout
from io import StringIO

from pyshex.shex_evaluator import evaluate_cli


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))


@pytest.mark.xfail(reason="Fragile test - we need local data to consistently reproduce")
def test_failures_have_no_empty_reason_lines() -> None:
    """Issue #30: failures should never produce a 'Reason:' line with no content."""
    shex = os.path.join(DATA_DIR, 'biolink-model.shex')
    sparql = os.path.join(DATA_DIR, 'biolink_model.sparql')

    messages = StringIO()
    with redirect_stdout(messages):
        evaluate_cli(
            f'-ss -sq {sparql} http://graphdb.dumontierlab.com/repositories/ncats-red-kg {shex} -ut -pb'
        )

    empty_reason_lines = [
        line for line in messages.getvalue().splitlines()
        if line.strip().endswith('Reason:')
    ]
    assert not empty_reason_lines, f"Found {len(empty_reason_lines)} empty 'Reason:' line(s)"