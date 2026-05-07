from rdflib import Graph, Namespace, XSD, Literal

from pyshex import ShExEvaluator


FHIR = Namespace("http://hl7.org/fhir")
EX = Namespace("http://example.org/")

SHEX = f"""PREFIX : <{FHIR}>
PREFIX xsd: <{XSD}>

start = @:ObservationShape

:ObservationShape {{               # An Observation has:
  (:status xsd:integer* | :status xsd:string* )*
}}
"""


def test_no_infinite_loop_on_repeated_optional_group() -> None:
    """shex.js issue #16: evaluation should terminate on repeated optional shape groups."""
    g = Graph()
    g.add((EX.Obs1, FHIR.status, Literal("final")))
    results = ShExEvaluator(rdf=g, schema=SHEX, focus=EX.Obs1,
                            start=FHIR.ObservationShape, debug=False).evaluate()
    assert results[0].result