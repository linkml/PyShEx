from rdflib.namespace import FOAF

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_4_node_constraints import nodeSatisfiesValues
from pyshex.shape_expressions_language.p5_context import Context
from tests.utils.setup_test import rdf_header, EX, gen_rdf, setup_context


SHEX_1 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/NoActionIssueShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://schema.example/state",
      "valueExpr": {
        "type": "NodeConstraint", "values": [
          "http://schema.example/Resolved",
          "http://schema.example/Rejected" ] } } } ] }"""

SHEX_2 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/EmployeeShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://xmlns.com/foaf/0.1/mbox",
      "valueExpr": {
        "type": "NodeConstraint", "values": [
          {"value": "N/A"},
          { "type": "IriStemRange", "stem": "mailto:engineering-" },
          { "type": "IriStemRange", "stem": "mailto:sales-", "exclusions": [
              { "type": "IriStem", "stem": "mailto:sales-contacts" },
              { "type": "IriStem", "stem": "mailto:sales-interns" }
            ] }
        ] } } } ] }"""

SHEX_3 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/EmployeeShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://xmlns.com/foaf/0.1/mbox",
      "valueExpr": {
        "type": "NodeConstraint", "values": [
          { "type": "IriStemRange", "stem": {"type": "Wildcard"},
            "exclusions": [
              { "type": "IriStem", "stem": "mailto:engineering-" },
              { "type": "IriStem", "stem": "mailto:sales-" }
            ] }
        ] } } } ] }"""

RDF_1 = f"""{rdf_header}
:issue1 ex:state ex:Resolved .
:issue2 ex:state ex:Unresolved .
"""

RDF_2 = gen_rdf("""<issue3> foaf:mbox "N/A" .
<issue4> foaf:mbox <mailto:engineering-2112@a.example> .
<issue5> foaf:mbox <mailto:sales-835@a.example> .
<issue6> foaf:mbox "missing" .
<issue7> foaf:mbox <mailto:sales-contacts-999@a.example> .""")

RDF_3 = gen_rdf("""<issue8> foaf:mbox 123 .
<issue9> foaf:mbox <mailto:core-engineering-2112@a.example> .
<issue10> foaf:mbox <mailto:engineering-2112@a.example> .""")


def fail_reasons(cntxt: Context) -> list[str]:
    return [e.strip() for e in cntxt.current_node.fail_reasons(cntxt.graph)]


def test_values_iri_set() -> None:
    cntxt = setup_context(SHEX_1, RDF_1)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue1, EX.state)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert nodeSatisfiesValues(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue2, EX.state)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert not nodeSatisfiesValues(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Node: :Unresolved not in value set:\n'
        '\t {"values": ["http://schema.example/Resolved", "http://schema...'
    ]


def test_values_stem_range_with_exclusions() -> None:
    cntxt = setup_context(SHEX_2, RDF_2)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue3, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert nodeSatisfiesValues(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue4, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert nodeSatisfiesValues(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue6, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert not nodeSatisfiesValues(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Node: "missing" not in value set:\n'
        '\t {"values": [{"value": "N/A"}, {"stem": "mailto:engineering-"...'
    ]

    focus = cntxt.graph.value(EX.issue7, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert not nodeSatisfiesValues(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Node: <mailto:sales-contacts-999@a.example> not in value set:\n'
        '\t {"values": [{"value": "N/A"}, {"stem": "mailto:engineering-"...'
    ]


def test_values_wildcard_stem_with_exclusions() -> None:
    cntxt = setup_context(SHEX_3, RDF_3)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue8, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert nodeSatisfiesValues(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue9, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert nodeSatisfiesValues(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue10, FOAF.mbox)
    cntxt.current_node = ParseNode(nodeSatisfiesValues, nc, focus, cntxt)
    assert not nodeSatisfiesValues(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Node: <mailto:engineering-2112@a.example> not in value set:\n'
        '\t {"values": [{"stem": {"type": "Wildcard"}, "exclusions": [{"...'
    ]