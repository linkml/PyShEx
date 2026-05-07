from typing import Callable

from pyjsg.jsglib import JSGObject
from pyjsg.jsglib import isinstance_
from rdflib import BNode, URIRef, Graph

from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph, Node
from pyshex.utils.collection_utils import format_collection


class ParseNode:
    def __init__(self,
                 function: Callable[["Context", RDFGraph | Node, JSGObject], bool],
                 expr: JSGObject,
                 obj: RDFGraph | Node,
                 cntxt: "Context"):
        self.function = function
        self.expr = expr
        self.graph = obj if isinstance(obj, RDFGraph) else None
        self.node = obj if isinstance_(obj, Node) else None
        self.result: bool = None
        self._fail_reason: str | None = None
        self.reason_stack: list[tuple[BNode | URIRef, str | None]] = []
        self.nodes: list[ParseNode] = []
        self.n3m = cntxt.n3_mapper

    def dump_bnodes(self, g: Graph, node: BNode, indent: str, top: bool = True) -> list[str]:
        indent = indent + "  "
        collection = format_collection(g, node, 6)
        if collection is not None:
            return [indent + c for c in collection]
        rval = []
        if top:
            for s, p in g.subject_predicates(node):
                rval.append(f"{indent}  {self.n3m.n3(s)} {self.n3m.n3(p)} {self.n3m.n3(node)} .")
        for p, o in sorted(g.predicate_objects(node)):
            rval += [f"{indent}     {self.n3m.n3(node)} {self.n3m.n3(p)} {self.n3m.n3(o)} ."]
            if isinstance(o, BNode):
                rval += self.dump_bnodes(g, o, indent, top=False)
        return rval

    def fail_reasons(self, g: Graph, depth: int = 0) -> list[str]:
        def follow_reasons(d: int) -> list[str]:
            fr = []
            if self._fail_reason:
                fr.append(d * "  " + f"  {self._fail_reason}")
                d += 1
            for n in self.nodes:
                fr += n.fail_reasons(g, d)
            return fr

        rval = []
        for i in range(0, len(self.reason_stack)):
            node, shape_name = self.reason_stack[i]
            if not shape_name:
                shape_name = '(unnamed shape)'
            indent = (i+depth)*"  "
            rval.append(f"{indent}  Testing {self.n3m.n3(node)} against shape {shape_name}")
            if isinstance(node, BNode):
                rval += [f"{indent}  {self.n3m.n3(node)} context:"]
                rval += self.dump_bnodes(g, node, indent)
                rval[-1] = rval[-1] + '\n'
        rval += follow_reasons(depth + len(self.reason_stack))
        return rval

    def set_result(self, rval: bool) -> None:
        """ Set the result of the evaluation. If the result is true, prune all of the children that didn't cut it

        :param rval: Result of evaluation
        """
        self.result = rval
        if self.result:
            self.nodes = [pn for pn in self.nodes if pn.result]
