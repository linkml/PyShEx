import os
import pytest

from pyshex import ShExEvaluator
from CFGraph import CFGraph


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))


@pytest.fixture
def graph() -> CFGraph:
    g = CFGraph()
    g.open(os.path.join(BASE_DIR, 'validation', 'biolink-model.ttl'))
    return g


def test_biolink_shexeval(graph: CFGraph) -> None:
    evaluator = ShExEvaluator(
        graph,
        os.path.join(BASE_DIR, 'schemas', 'meta.shex'),
        "https://biolink.github.io/biolink-model/ontology/biolink.ttl",
        "http://bioentity.io/vocab/SchemaDefinition",
    )
    result = evaluator.evaluate(debug=False)

    failures = [rslt for rslt in result if not rslt.result]
    for failure in failures:
        print(f"Error: {failure.reason}")

    assert not failures, f"{len(failures)} ShEx validation failure(s) found"