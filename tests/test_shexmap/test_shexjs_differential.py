"""Differential tests against shex.js's ``@shexjs/extension-map``.

Set ``SHEXJS_EXTENSION_MAP`` to the package directory of a built shex.js checkout
(``…/shex.js/packages/extension-map``) to run them; they are skipped otherwise.  Each
manifest example is bound and materialized on both sides and the results compared:

* the frames of shex.js's bindings equal PyShEx's (the trees themselves are compared, blank
  node labels aside, in ``test_examples.py`` against the bindings shex.js recorded);
* shex.js materializes PyShEx's bindings JSON, ``@node`` included, to the expected graph;
* PyShEx materializes shex.js's bindings to the expected graph.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal
from rdflib.compare import isomorphic

from pyshex.shexmap import bind, loads, materialize, normalize
from tests.test_shexmap.test_examples import (MANIFEST, expected_output, focus_node, input_graph, label,
                                              node_and_shape, output_root, text)

SHEXJS = os.environ.get("SHEXJS_EXTENSION_MAP")
DRIVER = Path(__file__).parent / "shexjs_driver.js"
pytestmark = pytest.mark.skipif(not SHEXJS, reason="SHEXJS_EXTENSION_MAP not set")


def node_arg(term) -> str:
    """A node for the driver: rdflib's blank-node labels mean nothing to n3, so a blank focus is
    named "ROOT" (the data's one root) and a blank output root keeps its label (shex.js mints it)."""
    return f"_:{term}" if isinstance(term, BNode) else str(term)


def focus_arg(term) -> str:
    return "ROOT" if isinstance(term, BNode) else str(term)


def shexjs(mode: str, *args: str) -> str:
    env = {**os.environ, "SHEXJS_TEST_PORTS": os.environ.get("SHEXJS_TEST_PORTS", "11111")}
    proc = subprocess.run(["node", str(DRIVER), SHEXJS, mode, *args], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def canonical_frames(frames) -> list:
    """Frames as comparable JSON: sorted (variable, value) pairs, blank-node values reduced
    to a marker (their labels are implementation-specific)."""
    def val(v):
        if isinstance(v, BNode):
            return "_:"
        if isinstance(v, Literal):
            return {"value": str(v), "type": str(v.datatype) if v.datatype else None, "language": v.language}
        return str(v)
    return sorted(sorted((k, json.dumps(val(v), sort_keys=True)) for k, v in f.items()) for f in frames)


# known divergences, as strict xfails
DIVERGES: dict[str, str] = {}      # label -> why the two implementations are expected to differ


@pytest.fixture(scope="module", ids=label,
                params=[pytest.param(e, marks=pytest.mark.xfail(strict=True, reason=DIVERGES[label(e)]))
                        if label(e) in DIVERGES else e for e in MANIFEST])
def example(request, tmp_path_factory):
    entry = request.param
    d = tmp_path_factory.mktemp("shexjs")
    (d / "in.shex").write_text(text(entry, "schema"), encoding="utf-8")
    (d / "in.ttl").write_text(text(entry, "data"), encoding="utf-8")
    (d / "out.shex").write_text(text(entry, "outputSchema"), encoding="utf-8")
    return entry, d


def test_shexjs_binds_the_same_frames(example):
    entry, d = example
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    focus = focus_node(entry, graph)
    ours = bind(graph, text(entry, "schema"), focus, start=start)
    theirs = loads(shexjs("bind", str(d / "in.shex"), str(d / "in.ttl"), focus_arg(focus), start or "START"))
    assert canonical_frames(theirs.frames()) == canonical_frames(ours.frames())


def test_shexjs_materializes_our_bindings(example):
    entry, d = example
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    ours = bind(graph, text(entry, "schema"), focus_node(entry, graph), start=start)
    root, shape = output_root(entry)
    (d / "ours.json").write_text(json.dumps(ours.to_json()), encoding="utf-8")
    nt = shexjs("materialize", str(d / "out.shex"), str(d / "ours.json"), node_arg(root), shape or "START")
    got = Graph().parse(data=nt, format="nt")
    assert isomorphic(got, expected_output(entry)), nt


def test_we_materialize_shexjs_bindings(example):
    entry, d = example
    graph = input_graph(entry)
    _, start = node_and_shape(entry["queryMap"])
    focus = focus_node(entry, graph)
    theirs = loads(shexjs("bind", str(d / "in.shex"), str(d / "in.ttl"), focus_arg(focus), start or "START"))
    root, shape = output_root(entry)
    got = materialize(text(entry, "outputSchema"), theirs, root, start=shape)
    assert isomorphic(got, expected_output(entry)), got.serialize(format="turtle")
