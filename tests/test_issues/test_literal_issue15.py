from rdflib import Namespace, XSD
from pyshex import ShExEvaluator


EX = Namespace("http://example.org/")

SHEX = f"""PREFIX : <{EX}>
PREFIX xsd: <{XSD}>

start = @<A>

<A> {{:p1 xsd:string }}
"""

RDF_DATA = f"""PREFIX : <{EX}>

:d :p1 "final" .
"""


def test_no_infinite_loop() -> None:
    """shex.js issue #17: evaluation should terminate without an infinite loop."""
    results = ShExEvaluator(rdf=RDF_DATA, schema=SHEX, focus=EX.d).evaluate(debug=False)
    assert results[0].result