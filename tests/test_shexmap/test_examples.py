"""Run the ShExMap example manifests through pyshex.shexmap.

``examples`` are shex.js's; ``pyshex-examples`` add ambiguity, EXTENDS and inverse cases."""
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic

from pyshex.shexmap import AmbiguousBindingsError, bind, bind_all, dumps, loads, materialize

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples"
MANIFEST = [dict(e, _dir=str(d)) for d in (HERE / "examples", HERE / "pyshex-examples")
            for e in json.loads((d / "manifest.json").read_text(encoding="utf-8"))]
TURTLE_BASE = "http://a.example/turtle/"   # the base shex.js's test runner parses data with

# shex.js splits one binding record across two nesting levels in this example; PyShEx keeps
# a report's variables together.  Both materialize to the expected graph.
BINDINGS_LAYOUT_DIFFERS = {"BPPatient 2 levels / simple"}


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


def test_bindings_match_shexjs(example):
    entry, bindings = example
    if "expectedBindingsURL" not in entry:
        pytest.skip("no shex.js bindings recorded")
    expected = json.loads(path(entry, entry["expectedBindingsURL"]).read_text(encoding="utf-8"))
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
