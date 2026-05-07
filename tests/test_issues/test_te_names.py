from pprint import pprint

from pyshex import ShExEvaluator


SHEX = """
prefix : <http://examples.org/ex/>

start = @<S3>

<S1> {$<S1TP> (:ex1a .; :ex1b .)}
<S2> {$<S2TP> (:ex2a .; :ex2b .)}
<S3> CLOSED {&<S1TP>; &<S2TP>;}
"""

PASSING = """
prefix : <http://examples.org/ex/>

:t :ex1a 1; :ex1b 2; :ex2a 3; :ex2b 4 .
"""

FAILING_1 = """
prefix : <http://examples.org/ex/>

:t :ex1a 1; :ex1b 2; :ex2a 3 .
"""

FAILING_2 = """
prefix : <http://examples.org/ex/>

:t :ex1a 1; :ex1b 2; :ex2a 3; :ex2b 4; a :foo.
"""

FOCUS = "http://examples.org/ex/t"


def test_te_labels_passing() -> None:
    """Triple expression labels: conformant node should pass."""
    results = ShExEvaluator(rdf=PASSING, schema=SHEX, focus=FOCUS).evaluate(debug=False)
    pprint(results)
    assert results[0].result


def test_te_labels_failing_missing_predicate() -> None:
    """Triple expression labels: missing ex2b predicate should fail."""
    results = ShExEvaluator(rdf=FAILING_1, schema=SHEX, focus=FOCUS).evaluate()
    assert not results[0].result


def test_te_labels_failing_extra_type_arc() -> None:
    """Triple expression labels: extra rdf:type arc on CLOSED shape should fail."""
    results = ShExEvaluator(rdf=FAILING_2, schema=SHEX, focus=FOCUS).evaluate()
    assert not results[0].result