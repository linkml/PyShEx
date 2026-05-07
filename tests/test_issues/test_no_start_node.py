from rdflib import Graph, Namespace

from pyshex import ShExEvaluator


SHEX = """<http://a.example/S> {<http://a.example/p> not @<http://a.example/S>}"""
EX = Namespace("http://a.example/")


def make_graph() -> Graph:
    g = Graph()
    g.add((EX.x, EX.p, EX.x))
    return g


def test_no_start_node_fails() -> None:
    rslt = ShExEvaluator(rdf=make_graph(), schema=SHEX, focus=EX.x).evaluate()[0]
    assert not rslt.result
    assert rslt.reason.strip() == 'START node is not specified'


def test_bad_start_node_fails() -> None:
    rslt = ShExEvaluator(rdf=make_graph(), schema=SHEX, start=EX.c, focus=EX.x).evaluate()[0]
    assert not rslt.result
    assert rslt.reason.strip() == 'Shape: http://a.example/c not found in Schema'