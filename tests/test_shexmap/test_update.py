"""The triples a schema matched, the strong identity law, and updating a graph in place."""
import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import Bindings, MaterializationError, ThreadedMaterializer, bind, materialize
from pyshex.shexmap.cli import main

PREFIXES = """PREFIX : <http://a.example/>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
A = "http://a.example/"
V = "http://v.example/"
P = URIRef(A + "p")
NESTED = PREFIXES + ("start = @:P\n:P { :report @<R>* %Map:{ id(@node) %} }\n"
                     "<R> { :no . %Map:{ v:no %} ; :result @<Res>* %Map:{ id(@node) %} }\n<Res> { :sys . %Map:{ v:sys %} }")
DATA = (':p :report :r1, :r2 ; :other "not in the schema" . :r1 :no "one" ; :result [ :sys 100 ], [ :sys 101 ] ; :extra "x" . '
        ':r2 :no "two" .')


def turtle(text: str) -> Graph:
    return Graph().parse(data="PREFIX : <http://a.example/>\n" + text, format="turtle")


def test_bindings_report_the_triples_the_schema_matched():
    graph = turtle(DATA)
    bound = bind(graph, NESTED, P)
    assert set(bound.matched) < set(graph)
    left_out = {str(p).split("/")[-1] for _, p, _ in set(graph) - set(bound.matched)}
    assert left_out == {"other", "extra"}                           # what the schema does not govern
    assert (URIRef(A + "r2"), URIRef(A + "no"), Literal("two")) in bound.matched


def test_the_strong_identity_law():
    # materializing a schema's own bindings gives exactly the subgraph it selected
    graph = turtle(DATA)
    bound = bind(graph, NESTED, P)
    selected = Graph()
    for t in bound.matched:
        selected.add(t)
    assert isomorphic(materialize(NESTED, bound, P), selected)


OUT = PREFIXES + "start = @:Out\n:Out { :who . %Map:{ v:name %} ; :bp @<B>* }\n<B> { :sys . %Map:{ v:sys %} }"
ROOT = URIRef(A + "out")


def readings(graph: Graph) -> set:
    return {str(o) for _, _, o in graph.triples((None, URIRef(A + "sys"), None))}


def test_update_replaces_what_the_schema_holds_and_keeps_the_rest():
    graph = turtle(':out :unrelated "kept" . :elsewhere :who "someone else" .')
    first = Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("110")}, {V + "sys": Literal("111")}]])
    m = ThreadedMaterializer(OUT)
    added, removed = m.update(graph, first, ROOT)
    assert removed == set() and len(added) == 1 + 2 + 2
    assert readings(graph) == {"110", "111"}
    second = Bindings([{V + "name": Literal("Susan")}, [{V + "sys": Literal("110")}, {V + "sys": Literal("112")}]])
    added, removed = m.update(graph, second, ROOT)
    assert {str(o) for _, _, o in removed if isinstance(o, Literal)} == {"Sue", "111"}
    assert len(removed) == 2          # the old name and the old value; the reading's node, minted by position, stays
    assert readings(graph) == {"110", "112"}
    assert (ROOT, URIRef(A + "who"), Literal("Susan")) in graph and (ROOT, URIRef(A + "who"), Literal("Sue")) not in graph
    assert (ROOT, URIRef(A + "unrelated"), Literal("kept")) in graph                      # not governed: kept
    assert (URIRef(A + "elsewhere"), URIRef(A + "who"), Literal("someone else")) in graph  # another root: kept
    fresh = materialize(OUT, second, ROOT)
    fresh.add((ROOT, URIRef(A + "unrelated"), Literal("kept")))
    fresh.add((URIRef(A + "elsewhere"), URIRef(A + "who"), Literal("someone else")))
    assert isomorphic(graph, fresh)


def test_an_unchanged_input_changes_nothing():
    graph = Graph()
    b = Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("110")}, {V + "sys": Literal("111")}]])
    materialize(OUT, b, ROOT, graph=graph)
    before = set(graph)
    added, removed = ThreadedMaterializer(OUT).update(graph, b, ROOT)
    assert added == set() and removed == set() and set(graph) == before


def test_materialize_replace_is_update():
    graph = Graph()
    materialize(OUT, Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("110")}]]), ROOT, graph=graph)
    materialize(OUT, Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("120")}]]), ROOT, graph=graph, replace=True)
    assert readings(graph) == {"120"}
    materialize(OUT, Bindings([{V + "name": Literal("Sue")}, [{V + "sys": Literal("130")}]]), ROOT, graph=graph)
    assert readings(graph) == {"120", "130"}                        # without replace: added to


def test_a_root_that_does_not_conform_is_refused():
    graph = turtle(':out :who "Sue" , "Also Sue" .')                 # two names where the schema wants one
    with pytest.raises(MaterializationError, match="does not conform"):
        ThreadedMaterializer(OUT).update(graph, Bindings([{V + "name": Literal("Sue")}, []]), ROOT)


def test_cli_into(tmp_path):
    existing = tmp_path / "existing.ttl"
    existing.write_text('@prefix : <http://a.example/> .\n:out :unrelated "kept" ; :who "Old" .\n', encoding="utf-8")
    (tmp_path / "b.json").write_text('[{"http://v.example/name": {"value": "New"}}, []]', encoding="utf-8")
    (tmp_path / "out.shex").write_text(OUT, encoding="utf-8")
    assert main(["-j", str(tmp_path / "b.json"), "-t", str(tmp_path / "out.shex"), "-r", str(ROOT), "--into", str(existing)]) == 0
    g = Graph().parse(existing, format="turtle")
    assert (ROOT, URIRef(A + "who"), Literal("New")) in g and (ROOT, URIRef(A + "who"), Literal("Old")) not in g
    assert (ROOT, URIRef(A + "unrelated"), Literal("kept")) in g
