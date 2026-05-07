import re
from typing import Iterator

from rdflib import URIRef, BNode, Literal, Graph

#  This document assumes an understanding of the ShEx notation and terminology.
#
#     ShapeExpression: a Boolean expression of ShEx shapes.
#     focus node: a node, potentially in an RDF graph, to be inspected for conformance with a shape expression.
#
# ShExMap uses the following terms from RDF semantics [rdf11-mt]:
#
#     Node: one of IRI, blank node, Literal.
#     Graph: a set of Triples of (subject, predicate, object).


# We have no idea what is intended in the above definition -- for the moment we'll define it as a function
# ShapeExpression = Callable[[list[ShExJ.Shape], bool]]
Node = URIRef | BNode | Literal
FocusNode = Node
TripleSubject = URIRef | BNode
TriplePredicate = URIRef
TripleObject = URIRef | Literal | BNode
Triple = tuple[TripleSubject, TriplePredicate, TripleObject]


class RDFTriple(tuple):

    def __init__(self, _: Triple) -> None:
        super().__init__()

    @property
    def s(self) -> TripleSubject:
        return self[0]

    @property
    def p(self) -> TriplePredicate:
        return self[1]

    @property
    def o(self) -> TripleObject:
        return self[2]

    def __str__(self) -> str:
        return f"<{self.s}> <{self.p}> {self.o} ."


class RDFGraph(set):
    def __init__(self, ts: Iterator[RDFTriple] | Iterator[Triple] | None = None) -> None:
        super().__init__([t if isinstance(t, RDFTriple) else RDFTriple(t) for t in ts] if ts is not None else [])

    def __str__(self) -> str:
        g = Graph()
        [g.add((e.s, e.p, e.o)) for e in self]
        return re.sub(r'^@prefix.*', '', g.serialize(format="turtle").decode(), flags=re.MULTILINE).strip()

    def add_triples(self, triples: Iterator[Triple]):
        super().update([RDFTriple(t) for t in triples])
