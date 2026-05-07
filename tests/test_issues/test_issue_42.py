import pytest

from pyshex import ShExEvaluator, PrefixLibrary


SHEX = """
PREFIX ex: <http://example.org/ex/>
START = @<S>

<S> { ex:p . }
"""

RDF_DATA = """
BASE <http://example.org/ex/>

<s> <p> "Stuff" .
<a> <t> "Other stuff" .
"""

NUM_ITERS = 3


@pytest.fixture(scope="module")
def evaluator() -> ShExEvaluator:
    p = PrefixLibrary(SHEX)
    return ShExEvaluator(rdf=RDF_DATA, schema=SHEX, focus=p.EX.s)


@pytest.fixture(scope="module")
def pl() -> PrefixLibrary:
    return PrefixLibrary(SHEX)


def test_repeated_evaluate_conformant(evaluator: ShExEvaluator) -> None:
    """Issue #42: evaluate() should return consistent passing results across repeated calls."""
    for _ in range(NUM_ITERS):
        assert evaluator.evaluate()[0].result


def test_repeated_evaluate_nonconformant(evaluator: ShExEvaluator, pl: PrefixLibrary) -> None:
    """Issue #42: evaluate() should return consistent failing results across repeated calls."""
    for _ in range(NUM_ITERS):
        assert not evaluator.evaluate(focus=pl.EX.a)[0].result