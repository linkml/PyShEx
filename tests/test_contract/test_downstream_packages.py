"""Run the real downstream packages against this PyShEx, when they are installed.

These tests skip in the normal dev environment. The CI ``downstream`` job installs
PyShEx from this tree together with the latest linkml and jupyter-rdfify in a single
resolution, which also proves their dependency pins remain compatible with ours.
"""
import argparse
import importlib
import importlib.util
import sys
import types

import pytest
from rdflib import Graph

LINKML_SCHEMA = """
id: http://example.org/model
name: model
prefixes:
  linkml: https://w3id.org/linkml/
  ex: http://example.org/model/
default_prefix: ex
default_range: string
imports:
  - linkml:types
classes:
  Person:
    slots: [name, age]
slots:
  name:
    required: true
  age:
    range: integer
"""

TTL = """@prefix ex: <http://example.org/model/> .
@prefix p: <http://example.org/people/> .
p:42 a ex:Person ; ex:name "Joe" ; ex:age 42 .
p:43 a ex:Person ; ex:age "not a number" .
"""


def test_linkml_shexgen_output_validates_with_pyshex():
    pytest.importorskip("linkml")
    from linkml.generators.shexgen import ShExGenerator

    from pyshex.evaluate import evaluate

    shex = ShExGenerator(LINKML_SCHEMA).serialize(collections=False)
    g = Graph().parse(data=TTL, format="turtle")
    ok, reason = evaluate(g, shex, start="http://example.org/model/Person", focus="http://example.org/people/42")
    assert ok, reason
    ok, _ = evaluate(g, shex, start="http://example.org/model/Person", focus="http://example.org/people/43")
    assert not ok


def load_jupyter_rdfify_submodule(name: str):
    """Import a submodule of jupyter-rdfify without executing its package __init__.

    The distribution's import name is ``jupyter-rdfify`` (with a hyphen), and its __init__
    pulls in IPython display code and the ``cgi`` module, which Python 3.13 removed.
    Only the ShEx module matters to PyShEx.
    """
    spec = importlib.util.find_spec("jupyter-rdfify")
    if spec is None:
        pytest.skip("jupyter-rdfify is not installed")
    pkg_name = "_jupyter_rdfify_under_test"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = list(spec.submodule_search_locations)
        sys.modules[pkg_name] = pkg
    return importlib.import_module(f"{pkg_name}.{name}")


class RecordingLogger:
    def __init__(self):
        self.lines = []

    def out(self, msg, verbose=False, *_):
        self.lines.append(msg)

    def print(self, msg):
        self.lines.append(msg)


def test_jupyter_rdfify_shex_module():
    shex_module = load_jupyter_rdfify_submodule("shex")
    subparsers = argparse.ArgumentParser().add_subparsers()
    logger = RecordingLogger()
    module = shex_module.ShexModule("shex", subparsers, logger, "ShEx module", "ShEx")
    store = {
        "rdfshapes": {},
        "rdfgraphs": {"g": Graph().parse(data=TTL, format="turtle")},
    }

    def cell(action, cell=None, **kw):
        params = argparse.Namespace(action=action, cell=cell, label=None, graph=None, focus=None, start=None)
        vars(params).update(kw)
        module.handle(params, store)

    cell("prefix", "PREFIX ex: <http://example.org/model/>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>")
    cell("parse", "ex:Person { ex:name xsd:string ; ex:age xsd:integer ? }", label="s")
    assert "s" in store["rdfshapes"], logger.lines
    cell("validate", label="s", graph="g", start="http://example.org/model/Person",
         focus="http://example.org/people/42")
    assert "PASSED!" in logger.lines, logger.lines
    cell("validate", label="s", graph="g", start="http://example.org/model/Person",
         focus="http://example.org/people/43")
    assert any(line.startswith("FAILED!") for line in logger.lines), logger.lines
