from rdflib import URIRef, Literal
from rdflib.namespace import FOAF

from pyshex.shape_expressions_language.p3_terminology import arcsOut, arcsIn, neigh, predicatesIn, predicatesOut, predicates
from tests.utils.setup_test import rdf_header, setup_test, EX, INST


RDF_1 = f"""{rdf_header}
inst:Issue1 
    ex:state      ex:unassigned ;
    ex:reportedBy ex:User2 .

ex:User2
    foaf:name     "Bob Smith" ;
    foaf:mbox     <mailto:bob@example.org> .
"""


def test_arcs_and_neighbourhood() -> None:
    _, g = setup_test(None, RDF_1)

    assert arcsOut(g, EX.User2) == {
        (EX.User2, FOAF.mbox, URIRef('mailto:bob@example.org')),
        (EX.User2, FOAF.name, Literal('Bob Smith')),
    }
    assert arcsIn(g, EX.User2) == {
        (INST.Issue1, EX.reportedBy, EX.User2),
    }
    assert neigh(g, EX.User2) == {
        (EX.User2, FOAF.mbox, URIRef('mailto:bob@example.org')),
        (EX.User2, FOAF.name, Literal('Bob Smith')),
        (INST.Issue1, EX.reportedBy, EX.User2),
    }


def test_predicates() -> None:
    _, g = setup_test(None, RDF_1)

    assert predicatesOut(g, EX.User2) == {FOAF.mbox, FOAF.name}
    assert predicatesIn(g, EX.User2) == {EX.reportedBy}
    assert predicates(g, EX.User2) == {FOAF.mbox, FOAF.name, EX.reportedBy}