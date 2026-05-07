from rdflib import Namespace, XSD

from pyshex import ShExEvaluator


FHIR = Namespace("http://hl7.org/fhir/")

SHEX = f"""PREFIX : <{FHIR}>
PREFIX xsd: <{XSD}>

start = @<A>

<A> {{
  :predd xsd:string ;
  ( :test @<A>* | :test @<E>* );
  :test2 @<C> ;
}}
<E> {{ :prede xsd:string ; }}
<A> {{ :subject @<C> ; :preda xsd:string }}
<C> {{ :subject @<A> ; :predc xsd:string }}
"""

RDF_DATA = f"""PREFIX : <{FHIR}>
PREFIX xsd: <{XSD}>

:d :predd "final" ; :test <a> ; :test2 <c> .
<a> :subject   <c> ; :prede    "final" .
<c> :subject   <a> ; :predc    "final" .
"""


def test_no_infinite_loop_on_recursive_shape() -> None:
    """shex.js issue #16: evaluation should terminate on recursive/inconsistent shape references."""
    rslt = ShExEvaluator(rdf=RDF_DATA, schema=SHEX, focus=FHIR.d, debug=False).evaluate()
    print(rslt[0].reason)
    assert not rslt[0].result