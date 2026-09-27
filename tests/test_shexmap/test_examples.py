"""Run the ShExMap example manifests through pyshex.shexmap.

``examples`` are shex.js's; ``pyshex-examples`` add ambiguity, EXTENDS and inverse cases."""
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import NODE_KEY, AmbiguousBindingsError, bind, bind_all, dumps, loads, materialize, normalize

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
MANIFEST = [dict(e, _dir=str(d)) for d in (HERE / "examples", HERE / "pyshex-examples")
            for e in json.loads((d / "manifest.json").read_text(encoding="utf-8"))]
TURTLE_BASE = "http://a.example/turtle/"   # the base shex.js's test runner parses data with

# the stored bindings are what shex.js writes (packages/extension-map/examples, branch
# shexmap-scopes): the scope layout with @node; blank-node labels are the parser's


def label(entry) -> str:
    return f"{entry['schemaLabel']} / {entry['dataLabel']}"


def path(entry, name: str) -> Path:
    return Path(entry["_dir"]) / name


def text(entry, key: str) -> str:
    return entry[key] if key in entry else path(entry, entry[key + "URL"]).read_text(encoding="utf-8")


def node_and_shape(shape_map: str):
    m = re.match(r'^(<[^>]*>|_:\S+)@(START|<[^>]*>)$', shape_map.strip())
    return m.group(1), None if m.group(2) == "START" else m.group(2)[1:-1]


def focus_node(entry, graph: Graph):
    node, _ = node_and_shape(entry["queryMap"])
    if node.startswith("_:"):
        # the data's only root (a blank node the query map cannot name)
        objects = set(graph.objects())
        roots = {s for s in graph.subjects() if s not in objects}
        assert len(roots) == 1
        return roots.pop()
    base = re.search(r'(?im)^\s*BASE\s*<([^>]*)>', text(entry, "data"))
    return URIRef(urljoin(base.group(1) if base else TURTLE_BASE, node[1:-1]))


def output_root(entry):
    node, shape = node_and_shape(entry["outputShapeMap"])
    return (BNode(node[2:]) if node.startswith("_:") else URIRef(node[1:-1])), shape


def expected_output(entry, name: str | None = None) -> Graph:
    return Graph().parse(path(entry, name or entry["expectedOutputDataURL"]), format="turtle")


def input_graph(entry) -> Graph:
    return Graph().parse(data=text(entry, "data"), format="turtle", publicID=TURTLE_BASE)


@pytest.fixture(scope="module", params=MANIFEST, ids=label)
def example(request):
    entry = request.param
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    bindings = bind(graph, text(entry, "schema"), focus_node(entry, graph), start=start)
    return entry, bindings


def without_nodes(obj):
    """The tree without its ``@node`` keys, which shex.js does not write (yet)."""
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k != NODE_KEY}
    if isinstance(obj, list):
        return [without_nodes(e) for e in obj]
    return obj


def canonical(obj):
    """``without_nodes``, with blank-node values reduced to a marker (labels do not survive
    a trip through materialization) and each list's iterations sorted (ShEx matches bags;
    the order a neighbourhood is listed in follows the nodes' labels, which is arbitrary)."""
    if isinstance(obj, dict):
        return {k: ("_:" if isinstance(v, str) and v.startswith("_:") else v)
                for k, v in obj.items() if k != NODE_KEY}
    if isinstance(obj, list):
        items = [canonical(e) for e in obj]
        return sorted(items, key=lambda e: json.dumps(e, sort_keys=True))
    return obj


def nodes_in(obj) -> list[dict]:
    """Every object of the tree that carries ``@node``."""
    if isinstance(obj, dict):
        return [obj] if NODE_KEY in obj else []
    if isinstance(obj, list):
        return [d for e in obj for d in nodes_in(e)]
    return []


def test_bindings_match_shexjs(example):
    """The same tree as shex.js writes, @node included, blank-node labels aside."""
    entry, bindings = example
    if "expectedBindingsURL" not in entry:
        pytest.skip("no shex.js bindings recorded")
    expected = json.loads(path(entry, entry["expectedBindingsURL"]).read_text(encoding="utf-8"))
    assert with_bnode_marker(bindings.to_json()) == with_bnode_marker(expected)


def with_bnode_marker(obj):
    if isinstance(obj, dict):
        return {k: ("_:" if isinstance(v, str) and v.startswith("_:") else v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [with_bnode_marker(e) for e in obj]
    return obj


# examples whose input schema has a repeated shape-valued constraint, so their trees have lists
# of iterations, each of which must say which node it matched
HAS_ITERATIONS = {"BPPatient multi-bindings / simple", "BPPatient 2 levels / simple", "splits / Ann-phone-mbox",
                  "splits / Ann-mbox-phone", "inverse in / Ann's heart rate", "inverse out / Ann's chart",
                  "EXTENDS / clinic"}
BP = "http://shex.io/extensions/Map/#BPDAM-"


def test_iterations_carry_the_node_they_matched(example):
    entry, bindings = example
    found = nodes_in(bindings.to_json())
    if label(entry) not in HAS_ITERATIONS:
        assert found == []
        return
    assert found
    for d in found:
        assert isinstance(d[NODE_KEY], str)                     # an IRI or a _:label, never a literal
    if label(entry) == "BPPatient 2 levels / simple":
        # the constraint that made the list also bound the node itself: the two must agree
        assert {d[NODE_KEY] for d in found} == {d.get(BP + "reports") or d.get(BP + "bp") for d in found}
        assert len(found) == 6                                  # two reports, four readings
    if label(entry) == "BPPatient multi-bindings / simple":
        assert all(d[NODE_KEY] == d[BP + "XXX"] for d in found)
    if label(entry) == "inverse in / Ann's heart rate":
        assert all(d[NODE_KEY].startswith("http://") for d in found)   # ^:subject binds subjects


def test_nodes_survive_json(example):
    entry, bindings = example
    assert loads(dumps(bindings)).to_json() == bindings.to_json()
    assert normalize(loads(dumps(bindings)).tree) == bindings.frames()
    assert not any(NODE_KEY in f for f in bindings.frames())


@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_bindings_survive_a_round_trip_through_the_input_schema(entry):
    """bind after materialize after bind is bind: materializing bindings with the *input*
    schema gives a graph that binds to the same bindings, i.e. a schema maps to itself.
    Compared as the set of parses, since an ambiguous input may parse in another order."""
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    focus = focus_node(entry, graph)
    schema = text(entry, "schema")
    before = {json.dumps(canonical(b.to_json()), sort_keys=True) for b in bind_all(graph, schema, focus, start=start)}
    root = BNode() if isinstance(focus, BNode) else focus
    out = materialize(schema, bind(graph, schema, focus, start=start), root, start=start)
    after = {json.dumps(canonical(b.to_json()), sort_keys=True) for b in bind_all(out, schema, root, start=start)}
    assert after == before, out.serialize(format="turtle")


def test_output_matches_shexjs(example):
    entry, bindings = example
    root, shape = output_root(entry)
    out = materialize(text(entry, "outputSchema"), bindings, root, start=shape)
    assert isomorphic(out, expected_output(entry)), out.serialize(format="turtle")


def test_bindings_survive_json(example):
    entry, bindings = example
    root, shape = output_root(entry)
    out = materialize(text(entry, "outputSchema"), loads(dumps(bindings)), root, start=shape)
    assert isomorphic(out, expected_output(entry))


@pytest.mark.parametrize("entry", [e for e in MANIFEST if "expectedBindingsURL" in e], ids=label)
def test_materialize_from_shexjs_bindings(entry):
    """Bindings JSON written by shex.js materializes to the same graph here."""
    root, shape = output_root(entry)
    bindings = loads(path(entry, entry["expectedBindingsURL"]).read_text(encoding="utf-8"))
    assert isomorphic(materialize(text(entry, "outputSchema"), bindings, root, start=shape), expected_output(entry))


@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_every_parse_and_its_output(entry):
    """bind_all finds each distinct parse; bind reports the count; strict refuses ambiguity."""
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    focus = focus_node(entry, graph)
    alternatives = bind_all(graph, text(entry, "schema"), focus, start=start)
    expected = entry.get("alternativeOutputDataURLs", [entry["expectedOutputDataURL"]])
    assert len(alternatives) == len(expected)
    root, shape = output_root(entry)
    for bindings, name in zip(alternatives, expected):
        assert isomorphic(materialize(text(entry, "outputSchema"), bindings, root, start=shape),
                          expected_output(entry, name))
    assert bind(graph, text(entry, "schema"), focus, start=start).alternatives == len(expected)
    if len(expected) > 1:
        with pytest.raises(AmbiguousBindingsError) as e:
            bind(graph, text(entry, "schema"), focus, start=start, strict=True)
        assert len(e.value.alternatives) == len(expected)
