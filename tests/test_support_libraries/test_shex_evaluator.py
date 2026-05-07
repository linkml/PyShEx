import os
from rdflib import Graph, URIRef

from pyshex import ShExEvaluator, PrefixLibrary
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START

shex_schema = """
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

loc_prefixes = PrefixLibrary(None,
                             wikidata="http://www.wikidata.org/entity/",
                             gw="http://genewiki.shape/")


def test_empty_constructor():
    evaluator = ShExEvaluator()
    assert evaluator.rdf.strip() == ""
    assert evaluator.schema is None
    assert evaluator.focus is None
    assert evaluator.foci == []
    assert evaluator.start == [START]
    assert evaluator.rdf_format == "turtle"
    assert isinstance(evaluator.g, Graph)


def test_complete_constructor():
    test_rdf = os.path.join(os.path.split(os.path.abspath(__file__))[0], '..', 'test_issues', 'data', 'Q18557122.ttl')
    evaluator = ShExEvaluator(test_rdf, shex_schema,
                              [loc_prefixes.WIKIDATA, loc_prefixes.WIKIDATA.Q18557112],
                              loc_prefixes.WIKIDATA.cancer)
    results = evaluator.evaluate()
    assert not results[0].result
    assert results[0].focus == URIRef('http://www.wikidata.org/entity/')
    assert results[0].start == URIRef('http://www.wikidata.org/entity/cancer')
    assert results[0].reason == 'Focus: http://www.wikidata.org/entity/ not in graph'
    assert results[1].focus == URIRef('http://www.wikidata.org/entity/Q18557112')
    assert results[1].start == URIRef('http://www.wikidata.org/entity/cancer')
    assert results[1].reason == '  Shape: http://www.wikidata.org/entity/cancer not found in Schema'