from rdflib import URIRef

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_4_node_constraints import nodeSatisfiesNumericFacet
from pyshex.shape_expressions_language.p5_context import Context
from tests.utils.setup_test import EX, gen_rdf, setup_context


SHEX_1 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/IssueShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://schema.example/confirmations",
      "valueExpr": { "type": "NodeConstraint", "mininclusive": 1 } } } ] }"""

SHEX_2 = """{
  "@context": "http://www.w3.org/ns/shex.jsonld",
  "type": "Schema",
  "shapes": [
    {
      "id": "http://a.example/S1",
      "type": "Shape",
      "expression": {
        "type": "TripleConstraint",
        "predicate": "http://a.example/p1",
        "valueExpr": {
          "type": "NodeConstraint",
          "nodeKind": "literal",
          "fractiondigits": 4
        }
      }
    }
  ]
}"""

RDF_1 = gen_rdf("""
:issue1 ex:confirmations 1 .
:issue2 ex:confirmations "2"^^xsd:byte .
:issue3 ex:confirmations 0 .
:issue4 ex:confirmations "ii"^^ex:romanNumeral .""")

RDF_2 = gen_rdf("""<http://a.example/s1>
<http://a.example/p1> "1.23450"^^<http://www.w3.org/2001/XMLSchema#decimal> .""")


def fail_reasons(cntxt: Context) -> list[str]:
    return [e.strip() for e in cntxt.current_node.fail_reasons(cntxt.graph)]


def test_numeric_facet_mininclusive() -> None:
    cntxt = setup_context(SHEX_1, RDF_1)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue1, EX.confirmations)
    cntxt.current_node = ParseNode(nodeSatisfiesNumericFacet, nc, focus, cntxt)
    assert nodeSatisfiesNumericFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue2, EX.confirmations)
    cntxt.current_node = ParseNode(nodeSatisfiesNumericFacet, nc, focus, cntxt)
    assert nodeSatisfiesNumericFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue3, EX.confirmations)
    cntxt.current_node = ParseNode(nodeSatisfiesNumericFacet, nc, focus, cntxt)
    assert not nodeSatisfiesNumericFacet(cntxt, focus, nc)
    assert fail_reasons(cntxt) == ['Numeric value volation - minimum inclusive: 1.0 actual: 0']


def test_numeric_facet_trailing_zero() -> None:
    cntxt = setup_context(SHEX_2, RDF_2)
    nc = cntxt.schema.shapes[0].expression.valueExpr
    focus = cntxt.graph.value(URIRef("http://a.example/s1"), URIRef("http://a.example/p1"))
    cntxt.current_node = ParseNode(nodeSatisfiesNumericFacet, nc, focus, cntxt)
    assert nodeSatisfiesNumericFacet(cntxt, focus, nc)