"""Bidirectionality: the round-trip laws of a schema pair, and the provenance that ties each
output triple to the input it came from."""
import json

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import Bindings, ThreadedMaterializer, bind, bind_all, materialize
from pyshex.shexmap.bindings import term_from_json
from pyshex.shexmap.cli import main
from pyshex.shexmap.scopes import ScopeTree
from tests.test_shexmap.test_examples import (MANIFEST, canonical, focus_node, input_graph, label, node_and_shape,
                                              output_root, text)

BY_LABEL = {label(e): e for e in MANIFEST}
PAIRS = [("BP / simple", "BP back / simple"), ("inverse in / Ann's heart rate", "inverse out / Ann's chart")]


def statics(entry) -> dict:
    return {k: term_from_json(v) for k, v in entry.get("staticVars", {}).items()}


def marker(v):
    return "_:" if isinstance(v, BNode) else v.n3()


def bound_pairs(bindings_list) -> set:
    return {(v, marker(x)) for b in bindings_list for s in ScopeTree(b.tree).root.walk() for v, x in s.own.items()}


def forward(entry):
    """bind with the input schema, materialize with the output schema."""
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    focus = focus_node(entry, graph)
    bindings = bind(graph, text(entry, "schema"), focus, start=start)
    root, shape = output_root(entry)
    m = ThreadedMaterializer(text(entry, "outputSchema"), static_vars=statics(entry))
    triples = m.materialize(bindings, root, start=shape)
    return graph, focus, bindings, m, triples, root, shape


# -- law 1: a schema binds back exactly what it wrote from -----------------------------

@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_the_output_schema_binds_back_what_it_read(entry):
    graph, focus, bindings, m, triples, root, shape = forward(entry)
    scopes = {s.path: s for s in ScopeTree(bindings.tree).root.walk()}
    read = {(v, marker(scopes[p].own[v])) for src in m.provenance for p, v in src["reads"]}
    read |= {(v, marker(m.statics[v])) for src in m.provenance for v in src["statics"]}
    out = Graph()
    for t in triples:
        out.add(t)
    rebound = bound_pairs(bind_all(out, text(entry, "outputSchema"), root, start=shape))
    assert rebound == read


# -- law 2: a pair of schemas, there and back --------------------------------------------

@pytest.mark.parametrize("there, back", PAIRS, ids=[f"{a} <-> {b}" for a, b in PAIRS])
def test_a_pair_recovers_the_bindings(there, back):
    ea, eb = BY_LABEL[there], BY_LABEL[back]
    graph, focus, bindings, _, triples, root, _ = forward(ea)
    middle = Graph()
    for t in triples:
        middle.add(t)
    _, start_back = node_and_shape(eb["queryMap"])
    b2 = bind(middle, text(eb, "schema"), root, start=start_back)
    _, shape_back = output_root(eb)
    _, start = node_and_shape(ea["queryMap"])
    returned = materialize(text(eb, "outputSchema"), b2, focus, start=shape_back, static_vars=statics(eb))
    original = {json.dumps(canonical(b.to_json()), sort_keys=True) for b in bind_all(graph, text(ea, "schema"), focus, start=start)}
    again = {json.dumps(canonical(b.to_json()), sort_keys=True) for b in bind_all(returned, text(ea, "schema"), focus, start=start)}
    assert again == original


def test_the_bp_pair_recovers_the_graph():
    # every node of the input is either the focus or carried by a variable, so the graph comes back as it was
    ea, eb = BY_LABEL["BP / simple"], BY_LABEL["BP back / simple"]
    graph, focus, _, _, triples, root, _ = forward(ea)
    middle = Graph()
    for t in triples:
        middle.add(t)
    _, start_back = node_and_shape(eb["queryMap"])
    _, shape_back = output_root(eb)
    returned = materialize(text(eb, "outputSchema"), bind(middle, text(eb, "schema"), root, start=start_back), focus,
                           start=shape_back, static_vars=statics(eb))
    assert isomorphic(returned, graph)


def test_the_inverse_pair_loses_only_uncarried_identities():
    # the chart carries no variable for the observation nodes, so they come back as blank nodes
    ea, eb = BY_LABEL["inverse in / Ann's heart rate"], BY_LABEL["inverse out / Ann's chart"]
    graph, focus, _, _, triples, root, _ = forward(ea)
    middle = Graph()
    for t in triples:
        middle.add(t)
    _, start_back = node_and_shape(eb["queryMap"])
    _, shape_back = output_root(eb)
    returned = materialize(text(eb, "outputSchema"), bind(middle, text(eb, "schema"), root, start=start_back), focus,
                           start=shape_back, static_vars=statics(eb))
    assert not isomorphic(returned, graph)
    blanked = Graph()
    observations = {s for s in graph.subjects() if s != focus}
    for s, p, o in graph:
        blanked.add((BNode(str(s)) if s in observations else s, p, BNode(str(o)) if o in observations else o))
    assert isomorphic(returned, blanked)


# -- provenance ---------------------------------------------------------------------------

PREFIXES = """PREFIX : <http://a.example/>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
V = "http://v.example/"
A = "http://a.example/"
OUT = URIRef(A + "out")


def test_every_triple_says_where_it_came_from():
    b = Bindings([{V + "name": Literal("Sue")},
                  [{"@node": URIRef(A + "r1"), V + "sys": Literal("110")}, {"@node": URIRef(A + "r2"), V + "sys": Literal("111")}]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :kind [:chart] ; :who . %Map:{ v:name %} ; "
                             ":bp @<R>* %Map:{ id(@node) %} }\n<R> { :sys . %Map:{ v:sys %} ; :owner . %Map:{ v:name %} }")
    triples = m.materialize(b, OUT)
    assert m.provenance is m.chosen.provenance and len(m.provenance) == len(triples)
    by_pred = {}
    for t, src in zip(triples, m.provenance):
        assert src["predicate"] == str(t[1])
        by_pred.setdefault(str(t[1]).split("/")[-1], []).append((t, src))
    assert by_pred["kind"][0][1]["constant"] is True and by_pred["kind"][0][1]["reads"] == ()
    (t, src), = by_pred["who"]
    assert src["variable"] == V + "name" and src["reads"] == (((), V + "name"),) and src["scope"] == ()
    for t, src in by_pred["bp"]:
        assert src["keyed"] == "id(@node)" and src["node"] == t[2]           # the keyed node is the input node
    for t, src in by_pred["sys"]:
        assert src["node"] == t[0] and src["reads"] == ((src["scope"], V + "sys"),)
    for t, src in by_pred["owner"]:
        assert src["reads"] == (((), V + "name"),) and src["scope"] != ()  # an inherited read, from the item


def test_structural_and_named_links_are_marked():
    b = Bindings({V + "n": Literal("x"), V + "who": URIRef(A + "alice")})
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :a @<S> ; :p @<P> %Map:{ v:who %} }\n<S> { :n . %Map:{ v:n %} }\n<P> { :k [:c] }")
    triples = m.materialize(b, OUT)
    kinds = {str(t[1]).split("/")[-1]: src for t, src in zip(triples, m.provenance)}
    assert kinds["a"].get("structural") is True
    assert kinds["p"].get("named") is True and kinds["p"]["variable"] == V + "who"


def test_cli_writes_provenance(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps({V + "n": {"value": "x"}}), encoding="utf-8")
    (tmp_path / "out.shex").write_text(PREFIXES + "start = @:Out\n:Out { :n . %Map:{ v:n %} ; :k [:c] }", encoding="utf-8")
    assert main(["-j", str(tmp_path / "b.json"), "-t", str(tmp_path / "out.shex"), "-r", str(OUT),
                 "-o", str(tmp_path / "out.ttl"), "--provenance", str(tmp_path / "prov.jsonl")]) == 0
    records = [json.loads(line) for line in (tmp_path / "prov.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["kind"] for r in records} == {"variable", "constant"}
    assert next(r for r in records if r["kind"] == "variable")["variable"] == V + "n"
