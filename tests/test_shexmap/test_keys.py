"""Node identity: keyed nodes (``id(...)``) merge, ``id(@node)`` reuses the input node, and
unkeyed nodes are reproducible."""
import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import Bindings, MaterializationError, ThreadedMaterializer, bind, materialize

PREFIXES = """PREFIX : <http://a.example/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
V = "http://v.example/"
A = "http://a.example/"
OUT = URIRef(A + "out")


def turtle(text: str) -> Graph:
    return Graph().parse(data="PREFIX : <http://a.example/>\n" + text, format="turtle")


def by_predicate(triples, local: str):
    return [(s, o) for s, p, o in triples if str(p) == A + local]


READINGS = Bindings([{}, [{V + "date": Literal("2026-09-01"), V + "sys": Literal("110")},
                          {V + "date": Literal("2026-09-01"), V + "sys": Literal("112")},
                          {V + "date": Literal("2026-09-02"), V + "sys": Literal("120")}]])


def test_equal_keys_merge_into_one_node():
    # readings bound flat; grouped by date on the way out
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :day @<Day>* %Map:{ id(v:date) %} }\n"
                             "<Day> { :date . %Map:{ v:date %} ; :reading . %Map:{ v:sys %} }")
    triples = m.materialize(READINGS, OUT)
    days = {o for _, o in by_predicate(triples, "day")}
    assert len(days) == 2
    readings = {(d, str(o)) for d, o in by_predicate(triples, "reading")}
    first = next(d for d, o in by_predicate(triples, "date") if str(o) == "2026-09-01")
    assert {r for d, r in readings if d == first} == {"110", "112"}
    assert len(by_predicate(triples, "date")) == 2                 # merged, not repeated


def test_a_key_of_one_iri_is_the_node():
    b = Bindings([{}, [{V + "who": URIRef(A + "alice"), V + "n": Literal("Alice")},
                       {V + "who": URIRef(A + "bob"), V + "n": Literal("Bob")}]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :member @<P>* %Map:{ id(v:who) %} }\n<P> { :name . %Map:{ v:n %} }")
    triples = m.materialize(b, OUT)
    assert {o for _, o in by_predicate(triples, "member")} == {URIRef(A + "alice"), URIRef(A + "bob")}
    assert (URIRef(A + "bob"), Literal("Bob")) in by_predicate(triples, "name")


def test_keyed_nodes_are_shared_across_constraints():
    b = Bindings([{V + "mrn": Literal("42"), V + "name": Literal("Ann")},
                  [{V + "when": Literal("Mon")}, {V + "when": Literal("Tue")}]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n"
                             ":Out { :patient @<P> %Map:{ id(v:mrn) %} ; :visit @<Visit>* }\n"
                             "<P> { :name . %Map:{ v:name %} }\n"
                             "<Visit> { :when . %Map:{ v:when %} ; :of @<P> %Map:{ id(v:mrn) %} }")
    triples = m.materialize(b, OUT)
    patient = by_predicate(triples, "patient")[0][1]
    assert {o for _, o in by_predicate(triples, "of")} == {patient}
    assert len(by_predicate(triples, "name")) == 1


def test_different_shapes_with_equal_keys_stay_apart():
    b = Bindings({V + "k": Literal("Paris")})
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :city @<City> %Map:{ id(v:k) %} ; :person @<Person> %Map:{ id(v:k) %} }\n"
                             "<City> { :kind [:city] }\n<Person> { :kind [:person] }")
    triples = m.materialize(b, OUT)
    assert by_predicate(triples, "city")[0][1] != by_predicate(triples, "person")[0][1]


NESTED = PREFIXES + ("start = @:P\n:P { :report @<R>* %Map:{ id(@node) %} }\n"
                     "<R> { :no . %Map:{ v:no %} ; :result @<Res>* %Map:{ id(@node) %} }\n"
                     "<Res> { :sys . %Map:{ v:sys %} }")
DATA = (':p :report :r1, :r2 . :r1 :no "one" ; :result [ :sys 100 ], [ :sys 101 ] . '
        ':r2 :no "two" ; :result [ :sys 110 ] .')


def test_id_node_maps_a_graph_onto_itself():
    graph = turtle(DATA)
    bound = bind(graph, NESTED, URIRef(A + "p"))                   # id() binds nothing on the way in
    out = materialize(NESTED, bound, URIRef(A + "p"))
    assert isomorphic(out, graph)
    assert (URIRef(A + "p"), URIRef(A + "report"), URIRef(A + "r1")) in out    # the very same IRIs


def test_unkeyed_nodes_are_reproducible_and_root_specific():
    b = Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("110")}, {V + "sys": Literal("111")}]])
    schema = PREFIXES + "start = @:Out\n:Out { :who . %Map:{ v:name %} ; :bp { :sys . %Map:{ v:sys %} }* }"
    once = ThreadedMaterializer(schema).materialize(b, OUT)
    again = ThreadedMaterializer(schema).materialize(b, OUT)
    assert once == again
    other = ThreadedMaterializer(schema).materialize(b, URIRef(A + "elsewhere"))
    assert {o for _, o in by_predicate(once, "bp")}.isdisjoint({o for _, o in by_predicate(other, "bp")})
    g = Graph()
    materialize(schema, b, OUT, graph=g)
    n = len(g)
    materialize(schema, b, OUT, graph=g)
    assert len(g) == n                                              # the same root twice adds nothing


def test_an_unbound_key_fails_the_constraint():
    b = Bindings({V + "name": Literal("Sue")})
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :who . %Map:{ v:name %} ; :home @<H>? %Map:{ id(v:city) %} }\n<H> { :kind [:home] }")
    triples = m.materialize(b, OUT)
    assert by_predicate(triples, "home") == []                      # optional: left out
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :home @<H> %Map:{ id(v:city) %} }\n<H> { :kind [:home] }")
    with pytest.raises(MaterializationError, match="city"):
        m.materialize(b, OUT)


@pytest.mark.parametrize("schema, message", [
    ("start = @:Out\n:Out { :n . %Map:{ id(v:k) %} }", "shape-valued"),
    ("start = @:Out\n:Out { :h @<H> %Map:{ id(v:k) %} %Map:{ v:k %} }\n<H> { :kind [:home] }", "only Map code"),
])
def test_id_is_alone_and_on_a_shape(schema, message):
    m = ThreadedMaterializer(PREFIXES + schema)
    with pytest.raises(MaterializationError, match=message):
        m.materialize(Bindings({V + "k": Literal("x")}), OUT)


# -- IRI templates ------------------------------------------------------------------------

def test_an_iri_template_names_the_node():
    b = Bindings([{V + "mrn": Literal("42"), V + "name": Literal("Ann")},
                  [{V + "when": Literal("Mon")}, {V + "when": Literal("Tue")}]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n"
                             ":Out { :patient @<P> %Map:{ id(<http://a.example/person/{v:mrn}>) %} ; :visit @<Visit>* }\n"
                             "<P> { :name . %Map:{ v:name %} }\n"
                             "<Visit> { :when . %Map:{ v:when %} ; :of @<P> %Map:{ id(<http://a.example/person/{v:mrn}>) %} }")
    triples = m.materialize(b, OUT)
    patient = URIRef(A + "person/42")
    assert by_predicate(triples, "patient") == [(OUT, patient)]
    assert {o for _, o in by_predicate(triples, "of")} == {patient}
    assert len(by_predicate(triples, "name")) == 1
    assert m.provenance[[t for t in triples].index((OUT, URIRef(A + "patient"), patient))]["reads"] == (((), V + "mrn"),)


def test_template_values_are_iri_safe():
    b = Bindings({V + "k": Literal("a b/c?d")})
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :x @<X> %Map:{ id(<http://a.example/k/{v:k}/tail>) %} }\n<X> { :kind [:c] }")
    assert by_predicate(m.materialize(b, OUT), "x") == [(OUT, URIRef(A + "k/a%20b%2Fc%3Fd/tail"))]


def test_an_unbound_template_variable_fails_the_constraint():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :x @<X> %Map:{ id(<http://a.example/k/{v:k}>) %} }\n<X> { :kind [:c] }")
    with pytest.raises(MaterializationError, match="v.example/k"):
        m.materialize(Bindings({V + "other": Literal("1")}), OUT)
