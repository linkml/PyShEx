"""Call patterns that jupyter-rdfify 1.0.4 (https://pypi.org/project/jupyter-rdfify/) uses.

It declares ``pyshex>=0.8.0`` and its ``%%rdf shex`` cell magic (``jupyter-rdfify/shex.py``) does:

    loader = SchemaLoader()                # pyshex.utils.schema_loader
    evaluator = ShExEvaluator()            # from pyshex import ShExEvaluator, no arguments
    schema = loader.loads(prefix + cell)   # ShExC text, prefixes stored in a separate cell
    for r in evaluator.evaluate(graph, schema, start=start, focus=focus):  # start/focus may be None
        r.start, r.focus, r.result, r.reason

The same evaluator instance is reused across cells. A parse error may either raise
or return None: jupyter-rdfify wraps ``loads`` in try/except and also checks for None.
"""
import pytest
from rdflib import Graph

from pyshex import ShExEvaluator
from pyshex.utils.schema_loader import SchemaLoader

PREFIX_CELL = """PREFIX ex: <http://example.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
SHAPE_CELL = """start = @ex:Person
ex:Person CLOSED { ex:name xsd:string ; ex:age xsd:integer ? }
"""
TTL = """@prefix ex: <http://example.org/> .
ex:alice ex:name "Alice" ; ex:age 42 .
ex:bob ex:name 17 .
"""
EX = "http://example.org/"


@pytest.fixture(scope="module")
def evaluator() -> ShExEvaluator:
    return ShExEvaluator()


@pytest.fixture(scope="module")
def schema():
    schema = SchemaLoader().loads(PREFIX_CELL + "\n" + SHAPE_CELL)
    assert schema is not None
    return schema


@pytest.fixture(scope="module")
def graph() -> Graph:
    return Graph().parse(data=TTL, format="turtle")


def summarize(results):
    return {(str(r.focus), str(r.start), r.result) for r in results}


def test_no_start_no_focus_evaluates_all_subjects(evaluator, schema, graph):
    results = evaluator.evaluate(graph, schema, start=None, focus=None)
    assert summarize(results) == {(EX + "alice", EX + "Person", True), (EX + "bob", EX + "Person", False)}
    failed = [r for r in results if not r.result]
    assert failed and isinstance(failed[0].reason, str) and failed[0].reason


def test_explicit_start_and_focus(evaluator, schema, graph):
    results = evaluator.evaluate(graph, schema, start=EX + "Person", focus=EX + "alice")
    assert summarize(results) == {(EX + "alice", EX + "Person", True)}


def test_focus_only_uses_schema_start(evaluator, schema, graph):
    results = evaluator.evaluate(graph, schema, start=None, focus=EX + "bob")
    assert summarize(results) == {(EX + "bob", EX + "Person", False)}


def test_parse_error_is_reported_as_none_or_exception():
    try:
        schema = SchemaLoader().loads(PREFIX_CELL + "ex:Broken { ex:name ")
    except Exception:
        return
    assert schema is None
