import datetime

from rdflib import Graph, URIRef, BNode, Namespace, RDF
from rdflib.namespace import DC
from rdflib.term import Node, Literal

header = """
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dc:   <http://purl.org/dc/terms/> .
@prefix earl: <http://www.w3.org/ns/earl#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix doap: <http://usefulinc.com/ns/doap#> .
@prefix ex:   <http://example.org/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

<https://pypi.org/project/PyShEx/> a doap:Project, earl:TestSubject, earl:Software ;
  doap:name          "PyShEx" ;
  doap:homepage      <https://github.com/hsolbrig/PyShEx> ;
  doap:license       <http://www.apache.org/licenses/LICENSE-2.0> ;
  doap:shortdesc     "Python implementation of ShEx"@en ;
  doap:description   "Python implementation of ShEx"@en ;
  doap:created       "2017-06-01"^^xsd:date ;
  doap:programming-language "Python" ;
  doap:implements    <https://shexspec.github.io/spec/> ;
  doap:category      <http://dbpedia.org/resource/Resource_Description_Framework> ;
  doap:download-page <https://pypi.org/project/PyShEx/> ;
  doap:mailing-list  <http://lists.w3.org/Archives/Public/public-shex-dev/> ;
  doap:bug-database  <http://github.com/hsolbrig/PyShEx/issues> ;
  doap:developer     <https://github.com/hsolbrig> ;
  doap:maintainer    <https://github.com/hsolbrig> ;
  doap:documenter    <https://github.com/hsolbrig> ;
  foaf:maker         <https://github.com/hsolbrig> ;
  dc:title           "PyShEx" ;
  dc:description     "Python implementation of ShEx"@en ;
  dc:date            "2018-11-13"^^xsd:date ;
  dc:creator         <https://github.com/hsolbrig> .
  
[] foaf:primaryTopic <http://github.com/hsolbrig/PyShEx> ;
  dc:issued "2018-11-13"^^xsd:date ;
  foaf:maker <https://github.com/hsolbrig> .

<https://github.com/hsolbrig> a foaf:Person, earl:Assertor;
  foaf:name "Harold Solbrig";
  foaf:title "Implementer";
  foaf:homepage <https://github.com/hsolbrig> ."""

EARL = Namespace("http://www.w3.org/ns/earl#")
MFST = Namespace("https://raw.githubusercontent.com/shexSpec/shexTest/master/validation/manifest#")


class EARLPage:
    def __init__(self, author: URIRef):
        self.g = Graph()
        self.g.parse(data=header, format="turtle")
        self.author = author

    def add(self, s: Node, p: URIRef, o: Node) -> "EARLPage":
        self.g.add((s, p, o))
        return self

    def add_test_result(self, test_entry: str, status: str) -> None:
        entry = BNode()
        self.add(entry, RDF.type, EARL.Assertion)\
            .add(entry, EARL.assertedBy, self.author)\
            .add(entry, EARL.test, MFST[test_entry])\
            .add(entry, EARL.subject, URIRef("https://pypi.org/project/PyShEx/"))\
            .add(entry, EARL.mode, EARL.automatic)
        self._add_result(entry, status)

    def _add_result(self, entry: BNode, status: bool) -> None:
        rslt = BNode()
        self.add(rslt, RDF.type, EARL.TestResult)\
            .add(rslt, EARL.outcome, EARL[status])\
            .add(rslt, DC.date, Literal(datetime.datetime.utcnow().isoformat()))\
            .add(entry, EARL.result, rslt)

    def __str__(self) -> str:
        return self.g.serialize(format="turtle").decode()


if __name__ == '__main__':
    p = EARLPage(URIRef("https://github.com/hsolbrig"))
    p.add_test_result('0', 'passed')
    print(str(p))
