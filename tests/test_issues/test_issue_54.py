import os
from pyshex import ShExEvaluator


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

RDF_DATA = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX SEMMEDDB: <http://example.org/UNKNOWN/SEMMEDDB/>
PREFIX WD: <http://example.org/UNKNOWN/WD/>

<http://identifiers.org/drugbank:DB00005> a WD:Q12140;
  rdfs:subClassOf <http://identifiers.org/mesh/D000602>;
  dcterms:description "Dimeric fusion protein consisting of ...";
  rdfs:label "Etanercept";
  <https://w3id.org/biolink/vocab/systematic_synonym> "BIOD00052" .
"""

FOCUS = "http://identifiers.org/drugbank:DB00005"
START = "https://w3id.org/biolink/vocab/Drug"
SHEX_FILE = os.path.join(DATA_DIR, 'shex', 'issue_54.shex')


def test_two_type_arcs_performance() -> None:
    """Issue #54: two possible type arcs in a definition should not cause a performance problem."""
    results = ShExEvaluator(rdf=RDF_DATA, schema=SHEX_FILE, focus=FOCUS, start=START).evaluate()
    assert results[0].result