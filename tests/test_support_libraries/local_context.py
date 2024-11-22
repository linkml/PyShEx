import sys
from rdflib import URIRef, XSD
from pyshex import PrefixLibrary

""" This module is used to test the PrefixLibrary's ability to inject namespaces directory into the containing module 
It is used in conjunction with test_prefixlib.test_add_to_module """

pl = PrefixLibrary("""
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
PREFIX pv: <http://www.wikidata.org/prop/value/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX gw: <http://genewiki.shape/>""")

pl.add_to_object(sys.modules[__name__])

def sample(name: str) -> URIRef:
    return PROV[name]

pl.add_rdf('@prefix XSD: <http://nonxml.com/item#> .')

pl.add_to_object(sys.modules[__name__], override=True)

def rdf(name: str) -> URIRef:
    return XSD[name]
