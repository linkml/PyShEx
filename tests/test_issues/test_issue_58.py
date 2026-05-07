from rdflib import Namespace

from pyshex import ShExEvaluator


UNIPROT = Namespace("http://identifiers.org/uniprot/")
BASE = Namespace("http://purl.obolibrary.org/obo/go/shapes/")

SHEX = """BASE   <http://purl.obolibrary.org/obo/go/shapes/>
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX GoBiologicalProcess: <http://purl.obolibrary.org/obo/GO_0008150>

<OwlClass> {
  rdf:type [ owl:Class ] {1};
}

<BiologicalProcessClass> IRI @<OwlClass> AND EXTRA rdfs:subClassOf {
  rdfs:subClassOf [ GoBiologicalProcess: ] ;
}
"""

RDF_DATA = """
@prefix : <http://model.geneontology.org/gorule6/> .
@prefix M: <http://purl.obolibrary.org/obo/GO_0097325> .
@prefix bl: <https://w3id.org/biolink/vocab/> .
@prefix contributor: <http://purl.org/dc/elements/1.1/contributor> .
@prefix date: <http://purl.org/dc/elements/1.1/date> .
@prefix enabled_by: <http://purl.obolibrary.org/obo/RO_0002333> .
@prefix evidence: <http://geneontology.org/lego/evidence> .
@prefix exact_match: <http://www.w3.org/2004/02/skos/core#exactMatch> .
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix occurs_in: <http://purl.obolibrary.org/obo/BFO_0000066> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix part_of: <http://purl.obolibrary.org/obo/BFO_0000050> .
@prefix provided_by: <http://purl.org/pav/providedBy> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix source: <http://purl.org/dc/elements/1.1/source> .
@prefix with: <http://geneontology.org/lego/evidence-with> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xref: <http://www.geneontology.org/formats/oboInOwl#hasDbXref> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

:i a <http://identifiers.org/uniprot/Q13253>, owl:NamedIndividual .

<http://identifiers.org/uniprot/Q13253> a owl:Class ;
    rdfs:subClassOf <http://identifiers.org/uniprot/Q13253>,
        obo:BFO_0000002,
        obo:BFO_0000004,
        obo:BFO_0000030,
        obo:BFO_0000040,
        obo:CHEBI_23367,
        obo:CHEBI_24431,
        obo:CHEBI_33285,
        obo:CHEBI_33302,
        obo:CHEBI_33579,
        obo:CHEBI_33582,
        obo:CHEBI_33675,
        obo:CHEBI_33694,
        obo:CHEBI_33695,
        obo:CHEBI_33839,
        obo:CHEBI_35352,
        obo:CHEBI_36080,
        obo:CHEBI_36357,
        obo:CHEBI_50047,
        obo:CHEBI_50860,
        obo:CHEBI_51143,
        obo:GOCHE_15339,
        obo:GOCHE_22695,
        obo:GOCHE_39142,
        obo:GOCHE_50906,
        obo:GOCHE_51086,
        obo:PR_000018263,
        <http://purl.obolibrary.org/obo/GO_0008150>,
        owl:Thing .
"""


def test_biological_process_class_passes() -> None:
    results = ShExEvaluator(
        rdf=RDF_DATA,
        schema=SHEX,
        focus=UNIPROT.Q13253,
        start=BASE.BiologicalProcessClass,
    ).evaluate()
    assert results[0].result