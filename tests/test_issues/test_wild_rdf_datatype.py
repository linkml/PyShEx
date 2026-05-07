from rdflib import Graph, Literal

RDF_DATA = '<x> <y> "ab"^^<http://a.example/bloodType>.'


def test_nonstandard_datatype_preserved() -> None:
    """Non-standard datatypes should be preserved as-is by rdflib."""
    g = Graph()
    ts = g.parse(data=RDF_DATA, format="turtle")
    assert list(ts.objects())[0] == Literal('ab', datatype='http://a.example/bloodType')
