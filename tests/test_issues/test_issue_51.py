from rdflib import Namespace, RDF

from pyshex import ShExEvaluator


BASE = Namespace("https://w3id.org/biolink/vocab/")

RDF_DATA = f"""
@prefix : <{BASE}> .
@prefix rdf: <{RDF}> .
:s rdf:type :X .
"""

SHEX = f"""
BASE <{BASE}>

<BiologicalProcess> ( 
    {{
        ( $<BiologicalProcess_tes> a [ <BiologicalProcessOrActivity> ] ?;
          a [ <BiologicalProcess> ]
        )
    }} OR @<X>
)

<X> {{&<BiologicalProcess_tes>; a [<X>]}}
"""

SHEX2 = f"""
BASE <{BASE}>

<BiologicalProcess> ( 
    {{
        ( $<BiologicalProcess_tes> a [ <BiologicalProcessOrActivity> ] ?;
          a [ <BiologicalProcess> ]
        )
    }} OR @<X>
)

<X> {{&<missing>}}
"""


def test_inner_triple_expression_recognised() -> None:
    """Issue #51: an inner triple expression should be recognised and pass validation."""
    results = ShExEvaluator(rdf=RDF_DATA, schema=SHEX, focus=BASE.s, start=BASE.X).evaluate()
    assert results[0].result


def test_missing_te_reference_fails_with_reason() -> None:
    """Issue #51: a reference to a missing triple expression should fail with a clear message."""
    results = ShExEvaluator(rdf=RDF_DATA, schema=SHEX2, focus=BASE.s, start=BASE.X).evaluate()
    assert not results[0].result
    assert results[0].reason == (
        '  Testing :s against shape https://w3id.org/biolink/vocab/X\n'
        '    https://w3id.org/biolink/vocab/missing: Reference not found'
    )