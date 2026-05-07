import os

from rdflib import Graph, Namespace

from pyshex import ShExEvaluator, PrefixLibrary
from pyshex.evaluate import evaluate


SHEX_SCHEMA = """
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
PREFIX pv: <http://www.wikidata.org/prop/value/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX gw: <http://genewiki.shape/>

start = @gw:cancer
gw:cancer {
  p:P1748 {
    prov:wasDerivedFrom @<reference>
  }+
}

<reference> {
  pr:P248  IRI ;
  pr:P813  xsd:dateTime ;
  pr:P699  LITERAL
}
"""

WIKIDATA = Namespace("http://www.wikidata.org/entity/")
TEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'Q18557122.ttl')


def test_wikidata_evaluate_function() -> None:
    g = Graph()
    g.parse(TEST_PATH, format="turtle")
    rslt, _ = evaluate(g, SHEX_SCHEMA, WIKIDATA.Q18557112)
    assert rslt


def test_wikidata_evaluator_class() -> None:
    pfx = PrefixLibrary(SHEX_SCHEMA, wikidata="http://www.wikidata.org/entity/")
    evaluator = ShExEvaluator(TEST_PATH, SHEX_SCHEMA, pfx.WIKIDATA.Q18557112)
    print(evaluator.evaluate(start=pfx.GW.cancer, debug=False))