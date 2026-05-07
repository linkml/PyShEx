from rdflib import Literal

from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFTriple, RDFGraph
from tests.utils.setup_test import EX, gen_rdf, setup_test

rdf_1 = gen_rdf("""
<issue1> ex:submittedOn "2016-07-08"^^xsd:date .
<issue2> ex:submittedOn "2016-07-08T01:23:45Z"^^xsd:dateTime .
<issue3> ex:submittedOn "2016-07"^^xsd:date .""")


rdf_out = """ns1:issue1 ns1:submittedOn "2016-07-08"^^xsd:date .

ns1:issue2 ns1:submittedOn "2016-07-08T01:23:45+00:00"^^xsd:dateTime .

ns1:issue3 ns1:submittedOn "2016-07-01"^^xsd:date ."""


def test_rdf_triple():
    x = RDFTriple((EX.issue1, EX.num, Literal(17)))
    assert x.s == EX.issue1
    assert x.p == EX.num
    assert x.o.value == 17
    assert str(x) == "<http://schema.example/issue1> <http://schema.example/num> 17 ."


def test_rdf_graph():
    x = RDFGraph([(EX.issue1, EX.count, Literal(17))])
    assert len(x) == 1
    x = RDFGraph([(EX.issue1, EX.count, Literal(17)), (EX.issue1, EX.count, Literal(17))])
    assert len(x) == 1
    x = RDFGraph([(EX.issue1, EX.count, Literal(17)), RDFTriple((EX.issue1, EX.count, Literal(17)))])
    assert len(x) == 1
    _, g = setup_test(None, rdf_1)
    x = RDFGraph(g)
    assert str(x) == rdf_out