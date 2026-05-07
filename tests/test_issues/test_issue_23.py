import pytest
from pyshex import ShExEvaluator, PrefixLibrary


SHEX = """
BASE <http://example.org/ex/>
PREFIX ex: <http://example.org/ex/>

start = @<S>

<S> { ex:p . }
"""

RDF = """
BASE <http://example.org/ex/>

<s> <p> "Stuff" .
"""


@pytest.fixture(scope="module")
def pl() -> PrefixLibrary:
    return PrefixLibrary(SHEX)


def test_focus_in_graph_passes(pl: PrefixLibrary) -> None:
    results = ShExEvaluator().evaluate(RDF, SHEX, focus=pl.EX.s, debug=False)
    assert results[0].result


def test_focus_not_in_graph_fails_with_reason(pl: PrefixLibrary) -> None:
    results = ShExEvaluator().evaluate(RDF, SHEX, focus=pl.EX.t)
    assert not results[0].result
    assert results[0].reason == "Focus: http://example.org/ex/t not in graph"


def test_mixed_focus_list_reports_per_focus(pl: PrefixLibrary) -> None:
    results = ShExEvaluator().evaluate(RDF, SHEX, focus=[pl.EX.s, pl.EX.t2])
    assert results[0].result
    assert not results[1].result
    assert results[1].reason == "Focus: http://example.org/ex/t2 not in graph"