import pytest
from contextlib import redirect_stdout
from io import StringIO
from typing import Callable

from rdflib import RDF, URIRef

from pyshex import ShExEvaluator
from pyshex.shex_evaluator import EvaluationResult, evaluate_cli
from tests.utils.SortoGraph import SortOGraph


RDF_DATA = '''
@prefix ex: <http://example.org/test/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:zrror1 rdf:type ex:S.
ex:pass1 rdf:type ex:S;
     ex:foo "a".
ex:pass2 rdf:type ex:S;
     ex:foo "b".
ex:zrror2 rdf:type ex:S.
ex:zrror3 rdf:type ex:S.
ex:zrror4 rdf:type ex:S.  
ex:pass3 rdf:type ex:S;
     ex:foo "c".
'''

SHEX = '''
PREFIX ex: <http://example.org/test/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> 
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> 
BASE <http://example.org/test/>

START=@<S>

<S> {a [ex:S]; ex:foo xsd:string}
'''

EXPECTED = [
    (URIRef('http://example.org/test/zrror1'),
     '  Testing ex:zrror1 against shape http://example.org/test/S\n'
     '       No matching triples found for predicate ex:foo'),
    (URIRef('http://example.org/test/zrror2'),
     '  Testing ex:zrror2 against shape http://example.org/test/S\n'
     '       No matching triples found for predicate ex:foo'),
    (URIRef('http://example.org/test/zrror3'),
     '  Testing ex:zrror3 against shape http://example.org/test/S\n'
     '       No matching triples found for predicate ex:foo'),
    (URIRef('http://example.org/test/zrror4'),
     '  Testing ex:zrror4 against shape http://example.org/test/S\n'
     '       No matching triples found for predicate ex:foo'),
]


@pytest.fixture(scope="module")
def graph() -> SortOGraph:
    g = SortOGraph()
    g.parse(data=RDF_DATA, format="turtle")
    return g


@pytest.fixture
def make_sink() -> Callable[[bool], tuple[Callable[[EvaluationResult], bool], list]]:
    """Returns a factory that produces a (sink, messages) pair."""
    def factory(fail_on_error: bool = False) -> tuple[Callable[[EvaluationResult], bool], list]:
        messages: list[tuple] = []

        def sink(r: EvaluationResult) -> bool:
            if not r.result:
                messages.append((r.focus, r.reason))
                return not fail_on_error
            return True

        return sink, messages

    return factory


def test_builtin_reports(graph: SortOGraph) -> None:
    """No output sink — failures are returned in results."""
    results = ShExEvaluator().evaluate(RDF_DATA, SHEX, focus=list(graph.subjects(RDF.type)))
    output = [(r.focus, r.reason) for r in results if not r.result]
    assert output == EXPECTED


def test_evaluate_sink_true(graph: SortOGraph, make_sink) -> None:
    """Sink returning True consumes failures; results list contains no failures."""
    sink, messages = make_sink()
    results = ShExEvaluator().evaluate(RDF_DATA, SHEX, focus=list(graph.subjects(RDF.type)),
                                       output_sink=sink)
    assert messages == EXPECTED
    assert [(r.focus, r.reason) for r in results if not r.result] == []


def test_evaluate_sink_false(graph: SortOGraph, make_sink) -> None:
    """Sink returning False on first failure halts evaluation after one error."""
    sink, messages = make_sink(True)
    ShExEvaluator().evaluate(graph, SHEX, focus=list(graph.subjects(RDF.type)),
                             output_sink=sink)
    assert len(messages) == 1
    assert messages[0][1] == EXPECTED[0][1]


def test_evaluator_sink(graph: SortOGraph, make_sink) -> None:
    """Sink passed to ShExEvaluator constructor behaves identically to evaluate()-level sink."""
    sink, messages = make_sink()
    results = ShExEvaluator(output_sink=sink).evaluate(graph, SHEX,
                                                       focus=list(graph.subjects(RDF.type)))
    assert messages == EXPECTED
    assert [(r.focus, r.reason) for r in results if not r.result] == []


def test_cli_stoponerror() -> None:
    messages = StringIO()
    with redirect_stdout(messages):
        assert evaluate_cli([RDF_DATA, SHEX, '-A', '-ut']) == 1
    assert messages.getvalue().strip() == """\
Errors:
  Focus: http://example.org/test/zrror1
  Start: http://example.org/test/S
  Reason:   Testing ex:zrror1 against shape http://example.org/test/S
       No matching triples found for predicate ex:foo

  Focus: http://example.org/test/zrror2
  Start: http://example.org/test/S
  Reason:   Testing ex:zrror2 against shape http://example.org/test/S
       No matching triples found for predicate ex:foo

  Focus: http://example.org/test/zrror3
  Start: http://example.org/test/S
  Reason:   Testing ex:zrror3 against shape http://example.org/test/S
       No matching triples found for predicate ex:foo

  Focus: http://example.org/test/zrror4
  Start: http://example.org/test/S
  Reason:   Testing ex:zrror4 against shape http://example.org/test/S
       No matching triples found for predicate ex:foo"""


def test_cli_stopafter_before_errors() -> None:
    """stopafter=2 halts before any errors are encountered (3 passing nodes come first)."""
    messages = StringIO()
    with redirect_stdout(messages):
        assert evaluate_cli([RDF_DATA, SHEX, '-A', '-ut', '--stopafter', '2']) == 0
    assert messages.getvalue() == ''


def test_cli_stopafter_at_pass_boundary() -> None:
    """stopafter=3 halts exactly at the last passing node — no errors reported."""
    messages = StringIO()
    with redirect_stdout(messages):
        assert evaluate_cli([RDF_DATA, SHEX, '-A', '-ut', '--stopafter', '3']) == 0


def test_cli_stopafter_hits_first_error() -> None:
    """stopafter=4 reaches the first failing node and reports exactly one error."""
    messages = StringIO()
    with redirect_stdout(messages):
        assert evaluate_cli([RDF_DATA, SHEX, '-A', '-ut', '--stopafter', '4']) == 1
    assert messages.getvalue().strip() == """\
Errors:
  Focus: http://example.org/test/zrror1
  Start: http://example.org/test/S
  Reason:   Testing ex:zrror1 against shape http://example.org/test/S
       No matching triples found for predicate ex:foo"""