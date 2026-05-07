from typing import Callable

from pyjsg.jsglib import JSGObject
from rdflib import URIRef

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_context import Context, DebugContext
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph, Node

# TODO: factor out common code below.  Differences are minor


def trace_satisfies(newline: bool=True, skip_trace: Callable[[JSGObject], bool]=lambda _: False):
    def e(f: Callable[[Context, Node, JSGObject, DebugContext], bool]):
        def wrapper(cntxt: Context, n: Node, expr: JSGObject) -> bool:
            parent_parse_node = cntxt.current_node
            cntxt.current_node = ParseNode(f, expr, n, cntxt)
            parent_parse_node.nodes.append(cntxt.current_node)
            c = cntxt.debug_context
            c.splus()
            if c.debug and not skip_trace(expr):
                c.print(c.i(0, f'--> {f.__name__} {c.d()} node: {cntxt.n3_mapper.n3(n)}'), not newline)
            rval = f(cntxt, n, expr, c)
            if c.debug and not skip_trace(expr):
                c.print(c.i(0, f'<-- {f.__name__} {c.d()} node: {cntxt.n3_mapper.n3(n)}: {rval}'))
            c.sminus()
            cntxt.current_node.set_result(rval)
            cntxt.current_node = parent_parse_node
            return rval
        return wrapper
    return e


def trace_matches(newline: bool=True):
    def e(f: Callable[[Context, RDFGraph, JSGObject, DebugContext, set[URIRef] | None], bool]):
        def wrapper(cntxt: Context, T: RDFGraph, expr: JSGObject, extras: set[URIRef] | None = None) -> bool:
            parent_parse_node = cntxt.current_node
            cntxt.current_node = ParseNode(f, expr, T, cntxt)
            parent_parse_node.nodes.append(cntxt.current_node)
            c = cntxt.debug_context
            c.splus()
            if c.debug:
                c.print(c.i(0, f'--> {f.__name__} {c.d()}'), not newline)
            rval = f(cntxt, T, expr, c, extras) if extras is not None else f(cntxt, T, expr, c)
            if c.debug:
                c.print(c.i(0, f'<-- {f.__name__} {c.d()} {rval}'))
            c.sminus()
            cntxt.current_node.result = rval
            cntxt.current_node = parent_parse_node
            return rval
        return wrapper
    return e


def trace_matches_tripleconstraint(newline: bool=True):
    def e(f: Callable[[Context, Node, JSGObject, DebugContext], bool]):
        def wrapper(cntxt: Context, n: Node, expr: JSGObject) -> bool:
            c = cntxt.debug_context
            c.splus()
            if c.debug:
                c.print(c.i(0, f'--> {f.__name__} {c.d()}'), not newline)
            rval = f(cntxt, n, expr, c)
            if c.debug:
                c.print(c.i(0, f'<-- {f.__name__} {c.d()} {rval}'))
            c.sminus()
            return rval
        return wrapper
    return e
