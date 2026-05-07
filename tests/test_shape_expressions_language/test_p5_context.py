from ShExJSG import ShExJ
from ShExJSG.ShExJ import IRIREF
from rdflib import URIRef, RDF

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.utils.schema_utils import predicates_in_expression
from tests.utils.setup_test import gen_rdf, setup_context

shex_1 = """
{ "type": "Schema",
  "shapes": [
     { "id": "http://schema.example/UserShape",
       "type": "Shape",
       "extra": ["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"],
       "expression": { "type": "TripleConstraint",
         "id" : "http://schema.example/te1",
         "predicate": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
         "valueExpr": { "type": "NodeConstraint",
                        "values": ["http://schema.example/Teacher"]
                      }
       }
     }
  ]
}"""

rdf_1 = gen_rdf(""" <Alice> ex:shoeSize "30"^^xsd:integer .
<Alice> a ex:Teacher .
<Alice> a ex:Person .
<SomeHat> ex:owner <Alice> .
<TheMoon> ex:madeOf <GreenCheese> .""")


def predicate_finder(predicates: list[URIRef], tc: ShExJ.TripleConstraint, cntxt: Context) -> None:
    if isinstance(tc, ShExJ.TripleConstraint):
        predicates.append(URIRef(tc.predicate))


def triple_expr_finder(predicates: list[URIRef], expr: ShExJ.shapeExpr, cntxt: Context) -> None:
    if isinstance(expr, ShExJ.Shape) and expr.expression is not None:
        cntxt.visit_triple_expressions(expr.expression, predicate_finder, predicates)


def test_basic_context():
    c = setup_context(shex_1, rdf_1)
    assert list(c.schema_id_map.keys()) == ['http://schema.example/UserShape']
    assert isinstance(list(c.schema_id_map.values())[0], ShExJ.Shape)
    assert list(c.te_id_map.keys()) == ['http://schema.example/te1']
    assert isinstance(list(c.te_id_map.values())[0], ShExJ.TripleConstraint)


def test_predicate_scan():
    c = setup_context(shex_1, rdf_1)
    predicates: list[URIRef] = []
    c.visit_shapes(c.shapeExprFor(IRIREF('http://schema.example/UserShape')), triple_expr_finder, predicates)
    assert predicates == [RDF.type]
    # Quick test of the utility function
    assert predicates_in_expression(c.shapeExprFor(IRIREF('http://schema.example/UserShape')), c) == \
           [ShExJ.IRIREF(str(u)) for u in predicates]