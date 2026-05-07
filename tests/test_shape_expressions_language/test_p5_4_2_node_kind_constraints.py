from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_4_node_constraints import nodeSatisfiesNodeKind
from pyshex.shape_expressions_language.p5_context import Context
from tests.utils.setup_test import rdf_header, EX, setup_context


SHEX_1 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/IssueShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint", "predicate": "http://schema.example/state",
      "valueExpr": { "type": "NodeConstraint", "nodeKind": "iri" } } } ] }"""

RDF_1 = f"""{rdf_header}
:issue1 ex:state ex:HunkyDory .
:issue2 ex:taste ex:GoodEnough .
:issue3 ex:state "just fine" .
"""


def fail_reasons(cntxt: Context) -> list[str]:
    return [e.strip() for e in cntxt.current_node.fail_reasons(cntxt.graph)]


def test_node_satisfies_node_kind() -> None:
    cntxt = setup_context(SHEX_1, RDF_1)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue1, EX.state)
    cntxt.current_node = ParseNode(nodeSatisfiesNodeKind, nc, focus, cntxt)
    assert nodeSatisfiesNodeKind(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue3, EX.state)
    cntxt.current_node = ParseNode(nodeSatisfiesNodeKind, nc, focus, cntxt)
    assert not nodeSatisfiesNodeKind(cntxt, focus, nc)
    assert fail_reasons(cntxt) == ['Node kind mismatch have: Literal expected: iri']