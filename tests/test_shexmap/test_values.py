"""Bound values against the output constraint's value expression: checked, retyped when a
plain literal's lexical form fits the datatype, otherwise failed like an unbound variable."""
import pytest
from rdflib import Graph, Literal, URIRef, XSD

from pyshex import ShExEvaluator
from pyshex.shexmap import Bindings, MaterializationError, ThreadedMaterializer

PREFIXES = """PREFIX : <http://a.example/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
V = "http://v.example/"
A = "http://a.example/"
OUT = URIRef(A + "out")


def run(schema: str, **bindings):
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n" + schema)
    return m, m.materialize(Bindings({V + k: v for k, v in bindings.items()}), OUT)


def objects(triples, local: str):
    return [o for _, p, o in triples if str(p) == A + local]


def test_a_plain_literal_is_retyped_to_the_constraint_datatype():
    _, triples = run(":Out { :n xsd:integer %Map:{ v:t %} }", t=Literal("42"))
    assert objects(triples, "n") == [Literal("42", datatype=XSD.integer)]


def test_a_typed_literal_that_satisfies_passes_unchanged():
    _, triples = run(":Out { :n xsd:integer %Map:{ v:t %} }", t=Literal("42", datatype=XSD.integer))
    assert objects(triples, "n") == [Literal("42", datatype=XSD.integer)]


def test_a_value_that_does_not_fit_fails_the_constraint():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :n xsd:integer %Map:{ v:t %} }")
    with pytest.raises(MaterializationError, match="does not satisfy"):
        m.materialize(Bindings({V + "t": Literal("not a number")}), OUT)
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :n xsd:integer %Map:{ v:t %} }")
    with pytest.raises(MaterializationError):                        # a typed literal is not retyped
        m.materialize(Bindings({V + "t": Literal("1", datatype=XSD.decimal)}), OUT)


def test_an_optional_constraint_is_left_out_and_a_disjunct_falls_through():
    _, triples = run(":Out { :n xsd:integer ? %Map:{ v:t %} ; :s . %Map:{ v:t %} }", t=Literal("abc"))
    assert objects(triples, "n") == [] and objects(triples, "s") == [Literal("abc")]
    _, triples = run(":Out { :n xsd:integer %Map:{ v:t %} | :s xsd:string %Map:{ v:t %} }", t=Literal("abc"))
    assert objects(triples, "n") == [] and objects(triples, "s") == [Literal("abc")]
    _, triples = run(":Out { :n xsd:integer %Map:{ v:t %} | :s xsd:string %Map:{ v:t %} }", t=Literal("7"))
    assert objects(triples, "n") == [Literal("7", datatype=XSD.integer)]


def test_value_sets_node_kinds_facets_and_references():
    _, triples = run(":Out { :k [:x :y] %Map:{ v:t %} }", t=URIRef(A + "x"))
    assert objects(triples, "k") == [URIRef(A + "x")]
    with pytest.raises(MaterializationError):
        run(":Out { :k [:x :y] %Map:{ v:t %} }", t=URIRef(A + "z"))
    with pytest.raises(MaterializationError):
        run(":Out { :k IRI %Map:{ v:t %} }", t=Literal("not an iri"))
    with pytest.raises(MaterializationError):
        run(":Out { :s xsd:string MINLENGTH 3 %Map:{ v:t %} }", t=Literal("ab"))
    _, triples = run(":Out { :n @<Int> %Map:{ v:t %} }\n<Int> xsd:integer", t=Literal("5"))
    assert objects(triples, "n") == [Literal("5", datatype=XSD.integer)]
    _, triples = run(":Out { :n xsd:integer AND MININCLUSIVE 0 %Map:{ v:t %} }", t=Literal("5"))
    assert objects(triples, "n") == [Literal("5", datatype=XSD.integer)]
    with pytest.raises(MaterializationError):
        run(":Out { :n xsd:integer AND MININCLUSIVE 0 %Map:{ v:t %} }", t=Literal("-5"))


def test_function_results_take_the_constraint_type():
    _, triples = run(':Out { :code xsd:integer %Map:{ hashmap(v:status, {"1": "Married", "2": "Single"}) %} }',
                     status=Literal("Single"))
    assert objects(triples, "code") == [Literal("2", datatype=XSD.integer)]


def test_the_output_conforms_to_the_output_schema():
    schema = ":Out { :n xsd:integer %Map:{ v:t %} ; :k [:x] %Map:{ v:k %} }"
    _, triples = run(schema, t=Literal("100"), k=URIRef(A + "x"))
    g = Graph()
    for t in triples:
        g.add(t)
    result = ShExEvaluator(rdf=g, schema=PREFIXES + "start = @:Out\n" + schema.replace("%Map:{ v:t %}", "").replace("%Map:{ v:k %}", ""),
                           focus=OUT).evaluate()
    assert result[0].result, result[0].reason


def test_the_check_can_be_turned_off():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :n xsd:integer %Map:{ v:t %} }", check_values=False)
    assert objects(m.materialize(Bindings({V + "t": Literal("not a number")}), OUT), "n") == [Literal("not a number")]
