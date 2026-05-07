import os
import pytest
from contextlib import redirect_stdout
from io import StringIO

from pyshex.shex_evaluator import evaluate_cli


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))


@pytest.mark.skip(reason="Fragile endpoint - has BNODES at the moment. This also takes a looong time")
def test_inline_sparql_no_carriage_return() -> None:
    """Issue #28: ensure inline SPARQL with no carriage return works."""
    shex = os.path.join(DATA_DIR, 'biolink-model.shex')
    sparql = 'select ?item where{graph ?g {?item a <http://w3id.org/biolink/vocab/Protein>}}'

    messages = StringIO()
    with redirect_stdout(messages):
        evaluate_cli(['-ss', '-sq', sparql,
                      'http://graphdb.dumontierlab.com/repositories/ncats-red-kg',
                      shex, '-ut', '-pb'])
    print(messages.getvalue())