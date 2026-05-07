import pytest
from pprint import pprint

from rdflib import Graph, Namespace

from pyshex import ShExEvaluator
from pyshex.evaluate import evaluate


RDF_DATA = """
@prefix : <http://example.org/model/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<http://example.org/context/42> a :Person ;
    foaf:age 43 ;
    foaf:firstName "Bob",
        "Joe" ;
    foaf:lastName "smith" .
"""

SHEX = """
<http://example.org/sample/example1/String> <http://www.w3.org/2001/XMLSchema#string>
<http://example.org/sample/example1/Int> <http://www.w3.org/2001/XMLSchema#integer>
<http://example.org/sample/example1/Boolean> <http://www.w3.org/2001/XMLSchema#boolean>
<http://example.org/sample/example1/Person> CLOSED {
    (  <http://xmlns.com/foaf/0.1/firstName> @<http://example.org/sample/example1/String> * ;
       <http://xmlns.com/foaf/0.1/lastName> @<http://example.org/sample/example1/String> ;
       <http://xmlns.com/foaf/0.1/age> @<http://example.org/sample/example1/Int> ? ;
       <http://example.org/model/living> @<http://example.org/sample/example1/Boolean> ? ;
       <http://xmlns.com/foaf/0.1/knows> @<http://example.org/sample/example1/Person> *
    )
}
"""

EXC = Namespace("http://example.org/context/")
EXE = Namespace("http://example.org/sample/example1/")


def test_closed_shape_fails() -> None:
    """Issue #41: CLOSED shape should reject the node due to undeclared rdf:type triple."""
    e = ShExEvaluator(rdf=RDF_DATA, schema=SHEX, focus=EXC['42'], start=EXE.Person)
    results = e.evaluate()
    pprint(results)
    assert not results[0].result


def test_closed_shape_via_evaluate_function() -> None:
    """Issue #41: evaluate() function should agree with ShExEvaluator on the CLOSED shape."""
    g = Graph()
    g.parse(data=RDF_DATA, format="turtle")
    results = evaluate(g, SHEX, focus=EXC['42'], start=EXE.Person)
    pprint(results)