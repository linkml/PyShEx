from pyjsg.jsglib import isinstance_
from rdflib import BNode, URIRef, Literal, Graph
from rdflib.namespace import NamespaceManager

from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Triple


class N3Mapper:
    def __init__(self, nsm: Graph | NamespaceManager = None) -> None:
        self._bnode_map: dict[BNode, str] = {}
        self.namespace_manager = NamespaceManager(Graph()) if nsm is None \
            else nsm.namespace_manager if isinstance(nsm, Graph) else nsm
        self._cur_bnode_number = 0

    @property
    def _next_bnode(self) -> str:
        self._cur_bnode_number += 1
        return f'_:b{self._cur_bnode_number}'

    def n3(self, node: URIRef | BNode | Literal | Triple | str) -> str:
        if isinstance_(node, Triple):
            return f"{self.n3(node[0])} {self.n3(node[1])} {self.n3(node[2])} ."
        elif isinstance(node, BNode):
            if node not in self._bnode_map:
                self._bnode_map[node] = self._next_bnode
            return self._bnode_map[node]
        else:
            if not isinstance(node, (URIRef, Literal)):
                node = URIRef(str(node))
            return node.n3(self.namespace_manager)


