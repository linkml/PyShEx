"""Call patterns that linkml (https://github.com/linkml/linkml) uses.

linkml declares ``pyshex >= 0.9.0`` and ``rdflib >= 7.6.0`` and supports Python >= 3.10.
Its usages, reproduced here with a small schema in the style of linkml's ShExGenerator:

* ``tests/linkml/test_generators/test_shexgen.py``:
  ``evaluate(g, shexstr, focus=node)`` for every subject ``node`` (a URIRef) in the graph,
  without a start shape. It must return, not raise.
* ``tests/linkml/test_notebooks/input/examples.py``:
  ``r = evaluate(g, shex, start=<str IRI>, focus=<str IRI>)`` then ``r[0]`` / ``r[1]``.
* ``tests/linkml/test_scripts/test_gen_shex.py``:
  ``ShExEvaluator(g, str(shex_file), focus, start).evaluate(debug=False)`` with positional
  arguments, then ``r.result`` / ``r.reason`` on each result.
"""
from rdflib import Graph, URIRef

from pyshex import ShExEvaluator
from pyshex.evaluate import evaluate

# Shaped like ShExGenerator output: BASE, prefixed IRIs, CLOSED/EXTRA shapes, rdf:type constraint.
SHEX = """BASE <http://example.org/model/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX schema: <http://schema.org/>
PREFIX linkml: <https://w3id.org/linkml/>

linkml:String xsd:string
linkml:Integer xsd:integer

<Person> CLOSED {
    (  $<Person_tes> (  schema:name @linkml:String ;
          schema:age @linkml:Integer ? ;
          <knows> @<Person> *
       ) ;
       rdf:type [ schema:Person ] ?
    )
}

<FriendlyPerson> CLOSED {
    (  $<FriendlyPerson_tes> (  &<Person_tes> ;
          rdf:type [ schema:Person ] ? ;
          <friend> @<Person> +
       ) ;
       rdf:type [ <FriendlyPerson> ] ?
    )
}
"""

TTL = """@prefix schema: <http://schema.org/> .
@prefix m: <http://example.org/model/> .
@prefix p: <http://example.org/people/> .

p:42 a schema:Person ; schema:name "Joe Smith" ; schema:age 42 .
p:43 a schema:Person ; schema:name "Jane" ; m:friend p:42 .
"""

PERSON = "http://example.org/model/Person"
FRIENDLY = "http://example.org/model/FriendlyPerson"
JOE = "http://example.org/people/42"
JANE = "http://example.org/people/43"


def graph() -> Graph:
    return Graph().parse(data=TTL, format="turtle")


def test_evaluate_with_string_iris_returns_indexable_pair():
    g = graph()
    r = evaluate(g, SHEX, start=PERSON, focus=JOE)
    assert r[0] is True, r[1]
    assert isinstance(r[1], str)

    r = evaluate(g, SHEX, start=FRIENDLY, focus=JOE)
    assert r[0] is False
    assert isinstance(r[1], str) and r[1]


def test_evaluate_every_subject_without_start_does_not_raise():
    g = graph()
    nodes = {s for s, _, _ in g}
    assert nodes
    for node in nodes:
        assert isinstance(node, URIRef)
        conforms, reason = evaluate(g, SHEX, focus=node)
        assert conforms is False  # this schema declares no start shape
        assert reason == "No starting shape"


def test_positional_evaluator_with_schema_file(tmp_path):
    shex_file = tmp_path / "model.shex"
    shex_file.write_text(SHEX, encoding="utf-8")
    results = ShExEvaluator(graph(), str(shex_file), JANE, FRIENDLY).evaluate(debug=False)
    assert all(r.result for r in results), [r.reason for r in results if not r.result]

    results = ShExEvaluator(graph(), str(shex_file), JOE, FRIENDLY).evaluate(debug=False)
    assert not all(r.result for r in results)
    assert all(isinstance(r.reason, str) for r in results)
