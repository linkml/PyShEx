import os

from rdflib import Namespace

from pyshex import ShExEvaluator

WIKIDATA = Namespace("http://www.wikidata.org/entity/")
TEST_DATA = os.path.join(os.path.split(os.path.abspath(__file__))[0], 'data')


def test_false_positive_minimum():
    with open(os.path.join(TEST_DATA, 'disease_min.shex')) as f:
        shex = f.read()
    e = ShExEvaluator(os.path.join(TEST_DATA, 'Q12214_min.ttl'), shex, WIKIDATA.Q12214, debug=False)
    assert not e.evaluate()[0].result


def test_false_positive_minimum_2():
    with open(os.path.join(TEST_DATA, 'disease_min.shex')) as f:
        shex = f.read()
    e = ShExEvaluator(os.path.join(TEST_DATA, 'Q12214_min_2.ttl'), shex, WIKIDATA.Q12214, debug=False)
    assert not e.evaluate()[0].result


def test_false_positive():
    with open(os.path.join(TEST_DATA, 'shex', 'disease.shex')) as f:
        shex = f.read()
    e = ShExEvaluator(os.path.join(TEST_DATA, 'Q12214.ttl'), shex, WIKIDATA.Q12214, debug=False)
    assert not e.evaluate()[0].result
