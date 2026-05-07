from rdflib import Literal
import pytest

from tests.utils.setup_test import setup_context


SHEX_1 = """{ "type": "Schema", "shapes": [
    { "id": "http://schema.example/IntConstraint",
      "type": "NodeConstraint",
      "datatype": "http://www.w3.org/2001/XMLSchema#integer"
    } ] }"""


@pytest.mark.skip(reason="SimpleExamplesTestCase not implemented")
def test_example_1() -> None:
    from pyshex.shape_expressions_language.p5_3_shape_expressions import satisfies
    cntxt = setup_context(SHEX_1, None)

    assert satisfies(cntxt, Literal('"30"^^<http://www.w3.org/2001/XMLSchema#integer>'), SHEX_1)
