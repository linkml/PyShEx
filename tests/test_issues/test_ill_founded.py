from rdflib import Graph, Namespace

from pyshex import ShExEvaluator

EX = Namespace("http://a.example/")


def test_false_positive_minimum():
    shex = """<http://a.example/S> {<http://a.example/p> @<http://a.example/S>}"""
    g = Graph()
    g.add((EX.x, EX.p, EX.x))
    e = ShExEvaluator(rdf=g, schema=shex, focus=EX.x, start=EX.S, debug=False)
    assert e.evaluate()[0].result


def test_inconsistent():
    shex = """<http://a.example/S> {<http://a.example/p> not @<http://a.example/S>}"""
    g = Graph()
    g.add((EX.x, EX.p, EX.x))
    e = ShExEvaluator(rdf=g, schema=shex, focus=EX.x, start=EX.S, debug=False)
    rslt = e.evaluate()
    assert not rslt[0].result
    assert rslt[0].reason.strip() == """\
Testing <http://a.example/x> against shape http://a.example/S
    Testing <http://a.example/x> against shape http://a.example/S
      http://a.example/S: Inconsistent recursive shape reference"""