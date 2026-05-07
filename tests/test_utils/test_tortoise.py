from rdflib import Graph, URIRef
from pyshex.utils import tortoise

tortoise.register()


def test_tortoise():
    g = Graph()

    result = g.serialize(format="tortoise")
    if isinstance(result, bytes):
        result = result.decode()

    assert result.strip() == """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .""".strip()

    g.bind("foo", "http://example.org/foo#")
    g.add(
        (
            URIRef("http://example.org/foo#a"),
            URIRef("http://example.org/foo#b"),
            URIRef("http://example.org/foo#c"),
        )
    )

    result = g.serialize(format="tortoise")
    if isinstance(result, bytes):
        result = result.decode()

    assert result.strip() == """@prefix foo: <http://example.org/foo#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

foo:a foo:b foo:c .""".strip()