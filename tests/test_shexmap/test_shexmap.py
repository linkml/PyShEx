"""Unit tests for pyshex.shexmap beyond the shex.js examples."""
import pytest
from rdflib import BNode, Graph, Literal, URIRef, XSD
from rdflib.compare import isomorphic

from pyshex.shexmap import (AmbiguousBindingsError, Bindings, MapFunctionError, MapValidationError,
                            MaterializationError, bind, bind_all, dumps, loads, map_graph, materialize)
from pyshex.shexmap.bindings import term_from_json, term_to_json
from pyshex.shexmap.functions import expand_variable, lift, lower

PREFIXES = """PREFIX : <http://a.example/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX v: <http://vars.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""


def turtle(text: str) -> Graph:
    return Graph().parse(data="PREFIX : <http://a.example/>\n" + text, format="turtle")


def iso(graph: Graph, text: str) -> bool:
    return isomorphic(graph, turtle(text))


A = URIRef("http://a.example/a")
OUT = URIRef("http://a.example/out")


# -- functions ------------------------------------------------------------------------

def test_regex_round_trip():
    code = "regex(/(?<v:family>[A-Za-z]+), (?<v:given>[A-Za-z]+)/)"
    bound = lift(code, Literal("Walker, Alice"), {"v": "http://vars.example/"})
    assert bound == {"http://vars.example/family": Literal("Walker"), "http://vars.example/given": Literal("Alice")}
    assert lower(code, bound.get, {"v": "http://vars.example/"}) == Literal("Walker, Alice")


def test_regex_lower_with_unbound_variable_is_none():
    assert lower("regex(/(?<v:x>.+)/)", {}.get, {"v": "http://vars.example/"}) is None


def test_hashmap_round_trip():
    code = 'hashmap(v:status, {"M": "Married", "S": "Single"})'
    bound = lift(code, Literal("S"), {"v": "http://vars.example/"})
    assert bound == {"http://vars.example/status": Literal("Single")}
    assert lower(code, bound.get, {"v": "http://vars.example/"}) == Literal("S")


@pytest.mark.parametrize("code", [
    "nosuch(v:x)",
    'hashmap(v:x, {"a": "same", "b": "same"})',
    "hashmap(v:x, not json)",
    "regex(/no capture groups/)",
])
def test_bad_function_calls(code):
    with pytest.raises(MapFunctionError):
        lift(code, Literal("a"), {"v": "http://vars.example/"})


def test_variable_names():
    assert expand_variable(" v:x ", {"v": "http://vars.example/"}) == "http://vars.example/x"
    assert expand_variable("<http://abs.example/y>", {}) == "http://abs.example/y"
    with pytest.raises(MapFunctionError):
        expand_variable("nope:x", {})


# -- binding and materializing ----------------------------------------------------------

def test_hashmap_maps_between_schemas():
    source = PREFIXES + ':S { :status ["M" "S"] %Map:{ hashmap(v:status, {"M": "Married", "S": "Single"}) %} }'
    target = PREFIXES + 'start = @:T\n:T { :maritalStatus xsd:string %Map:{ v:status %} }'
    graph = map_graph(turtle(':a :status "M" .'), source, A, target, OUT, start="http://a.example/S")
    assert iso(graph, ':out :maritalStatus "Married" .')


def test_failing_regex_fails_validation():
    source = PREFIXES + 'start = @:S\n:S { :name xsd:string %Map:{ regex(/(?<v:first>[a-z]+) (?<v:last>[a-z]+)/) %} }'
    with pytest.raises(MapValidationError) as e:
        bind(turtle(':a :name "NoSpaceHere" .'), source, A)
    assert "found no match" in str(e.value)


def test_nonconforming_focus_is_reported():
    source = PREFIXES + 'start = @:S\n:S { :name xsd:integer %Map:{ v:n %} }'
    with pytest.raises(MapValidationError):
        bind(turtle(':a :name "not a number" .'), source, A)


def test_inverse_triple_constraints():
    source = PREFIXES + 'start = @:S\n:S { ^:owns IRI %Map:{ v:owner %} }'
    target = PREFIXES + 'start = @:T\n:T { ^:ownedBy IRI %Map:{ v:owner %} }'
    graph = map_graph(turtle(':bob :owns :a .'), source, A, target, OUT)
    assert iso(graph, ':bob :ownedBy :out .')


def test_optional_constraints_without_bindings_are_skipped():
    source = PREFIXES + 'start = @:S\n:S { :name xsd:string %Map:{ v:name %} }'
    target = PREFIXES + 'start = @:T\n:T { :label xsd:string %Map:{ v:name %}; :note xsd:string ? %Map:{ v:note %} }'
    assert iso(map_graph(turtle(':a :name "A" .'), source, A, target, OUT), ':out :label "A" .')


def test_missing_required_binding_is_an_error():
    target = PREFIXES + 'start = @:T\n:T { :label xsd:string %Map:{ v:missing %} }'
    with pytest.raises(MaterializationError):
        materialize(target, {}, OUT)


def test_static_vars():
    target = PREFIXES + 'start = @:T\n:T { :version xsd:string %Map:{ <http://vars.example/version> %} }'
    graph = materialize(target, {}, OUT, static_vars={"http://vars.example/version": Literal("2")})
    assert iso(graph, ':out :version "2" .')


def test_repeated_values_become_repeated_triples():
    source = PREFIXES + 'start = @:S\n:S { :tag xsd:string * %Map:{ v:tag %} }'
    target = PREFIXES + 'start = @:T\n:T { :label xsd:string * %Map:{ v:tag %} }'
    graph = map_graph(turtle(':a :tag "x", "y", "z" .'), source, A, target, OUT)
    assert iso(graph, ':out :label "x", "y", "z" .')


def test_blank_node_root_and_focus():
    source = PREFIXES + 'start = @:S\n:S { :name xsd:string %Map:{ v:name %} }'
    target = PREFIXES + 'start = @:T\n:T { :label xsd:string %Map:{ v:name %} }'
    g = turtle('_:x :name "B" .')
    focus = next(iter(g.subjects()))
    out = map_graph(g, source, focus, target, "_:root")
    assert isinstance(next(iter(out.subjects())), BNode)
    assert iso(out, '[] :label "B" .')


# -- bindings structure -------------------------------------------------------------------

@pytest.mark.parametrize("term", [
    URIRef("http://a.example/x"),
    BNode("b1"),
    Literal("plain"),
    Literal("chat", lang="fr"),
    Literal("1.5", datatype=XSD.decimal),
])
def test_term_json_round_trip(term):
    assert term_from_json(term_to_json(term)) == term


def test_quoted_static_var_syntax():
    assert term_from_json('"123-456"') == Literal("123-456")
    assert term_from_json('"5"^^<http://www.w3.org/2001/XMLSchema#integer>') == Literal("5", datatype=XSD.integer)


def test_json_round_trip_keeps_structure():
    tree = [{"v:name": Literal("Sue")}, [{"v:x": Literal("1")}, {"v:x": Literal("2")}]]
    again = loads(dumps(Bindings(tree)))
    assert again.tree == tree
    assert [f["v:x"] for f in again.frames()] == [Literal("1"), Literal("2")]


def test_inverse_regex_is_checked_against_the_subject():
    source = PREFIXES + 'start = @:S\n:S { ^:owns IRI %Map:{ regex(/owner-(?<v:id>[0-9]+)$/) %} }'
    graph = map_graph(turtle(':owner-42 :owns :a .'), source, A,
                      PREFIXES + 'start = @:T\n:T { :ownerId . %Map:{ v:id %} }', OUT)
    assert iso(graph, ':out :ownerId "42" .')
    with pytest.raises(MapValidationError):
        bind(turtle(':someone :owns :a .'), source, A)


def test_ambiguous_input_is_reported():
    source = PREFIXES + 'start = @:S\n:S { :p . %Map:{ v:first %} ; :p . %Map:{ v:second %} }'
    g = turtle(':a :p "x", "y" .')
    found = bind_all(g, source, A)
    assert len(found) == 2
    assert {str(b.tree["http://vars.example/first"]) for b in found} == {"x", "y"}
    assert bind(g, source, A).ambiguous
    with pytest.raises(AmbiguousBindingsError):
        bind(g, source, A, strict=True)


def test_abstract_output_shape_without_extensions_is_an_error():
    target = PREFIXES + 'start = @:T\nABSTRACT :T { :x . %Map:{ v:x %} }'
    with pytest.raises(MaterializationError, match="abstract"):
        materialize(target, {"http://vars.example/x": Literal("1")}, OUT)
