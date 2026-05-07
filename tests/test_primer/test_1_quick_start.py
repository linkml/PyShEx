import pytest

from rdflib import Graph, Namespace

from pyshex.evaluate import evaluate


SHEXC = """PREFIX school: <http://school.example/#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX ex: <http://ex.example/#>

school:enrolleeAge xsd:integer MinInclusive 13 MaxInclusive 20

school:Enrollee {
  ex:hasGuardian IRI {1,2}
}
"""

RDF1 = """PREFIX ex: <http://ex.example/#>
PREFIX inst: <http://example.com/users/>

inst:Student1 ex:hasGuardian
  inst:Person2, inst:Person3 ."""

EX = Namespace("http://ex.example/#")
SCHOOL = Namespace("http://school.example/#")


@pytest.mark.skip(reason="Not yet implemented")
def test_first_example() -> None:
    g = Graph()
    g.parse(data=RDF1, format="turtle")
    rslt, reason = evaluate(g, SHEXC, EX.obs1, SCHOOL.Enrollee)
    assert rslt