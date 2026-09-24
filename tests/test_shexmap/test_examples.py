"""Run the shex.js extension-map examples through pyshex.shexmap."""
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import bind, dumps, loads, materialize

EXAMPLES = Path(__file__).parent / "examples"
MANIFEST = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
TURTLE_BASE = "http://a.example/turtle/"   # the base shex.js's test runner parses data with

# shex.js splits one binding record across two nesting levels in this example; PyShEx keeps
# a report's variables together.  Both materialize to the expected graph.
BINDINGS_LAYOUT_DIFFERS = {"BPPatient 2 levels / simple"}


def label(entry) -> str:
    return f"{entry['schemaLabel']} / {entry['dataLabel']}"


def text(entry, key: str) -> str:
    return entry[key] if key in entry else (EXAMPLES / entry[key + "URL"]).read_text(encoding="utf-8")


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


def expected_output(entry) -> Graph:
    return Graph().parse(EXAMPLES / entry["expectedOutputDataURL"], format="turtle")


@pytest.fixture(scope="module", params=MANIFEST, ids=label)
def example(request):
    entry = request.param
    graph = Graph().parse(data=text(entry, "data"), format="turtle", publicID=TURTLE_BASE)
    _, start = node_and_shape(entry["queryMap"])
    bindings = bind(graph, text(entry, "schema"), focus_node(entry, graph), start=start)
    return entry, bindings


def test_bindings_match_shexjs(example):
    entry, bindings = example
    expected = json.loads((EXAMPLES / entry["expectedBindingsURL"]).read_text(encoding="utf-8"))
    if label(entry) in BINDINGS_LAYOUT_DIFFERS:
        assert bindings.to_json() != expected   # if this starts failing, the layouts converged
    else:
        assert bindings.to_json() == expected


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


@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_materialize_from_shexjs_bindings(entry):
    """Bindings JSON written by shex.js materializes to the same graph here."""
    root, shape = output_root(entry)
    bindings = loads((EXAMPLES / entry["expectedBindingsURL"]).read_text(encoding="utf-8"))
    assert isomorphic(materialize(text(entry, "outputSchema"), bindings, root, start=shape), expected_output(entry))
