"""Collect ShExMap bindings from RDF that conforms to an input schema.

Bindings form a tree that mirrors how the data matched the schema.  Each node holds
the variables bound while matching one focus node against one shape.  A value matched
by a *repeated* triple constraint (max > 1), or by one iteration of a repeated group,
starts a *frame*: a child that keeps together everything bound from that value, so
that materialization can emit one output subtree per frame.

PyShEx finds a conformant partition of each neighbourhood by backtracking and does not
return it, so bindings are collected in a second pass after validation succeeds.  That
pass assigns each triple to the first triple constraint (in schema order) that it
satisfies and that still has room.  For schemas whose triple constraints can be told
apart by predicate and value -- as ShExMap schemas usually are -- this is the partition
validation found.  EXTENDS is not followed.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef, XSD
from rdflib.term import Node

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_3_shape_expressions import satisfies
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions

MAP_EXTENSION = "http://shex.io/extensions/Map/#"

UNBOUNDED_CAP = 50  # never expand "*" further than this (matches shex.js)


@dataclass
class BindingNode:
    """Variables bound while matching one node against one shape.

    :ivar vars: variable IRI -> bound RDF term, in binding order
    :ivar children: nested matches, in data order
    :ivar frame: whether this node came from a repeated match (see module docstring)
    """
    vars: dict[str, Node] = field(default_factory=dict)
    children: list[BindingNode] = field(default_factory=list)
    frame: bool = False

    def is_empty(self) -> bool:
        return not self.vars and all(c.is_empty() for c in self.children)

    def records(self) -> Iterable[tuple[BindingNode, dict[str, Node]]]:
        """Depth-first (node, vars) pairs."""
        yield self, self.vars
        for c in self.children:
            yield from c.records()

    # -- JSON, in the shape shex.js prints and reads ------------------------------------
    def to_json(self):
        """Non-repeated nested matches are merged into their parent's object; repeated ones
        become a list.  A tree without repetition is a single flat object."""
        merged = dict((k, term_to_json(v)) for k, v in self.vars.items())
        frames = []
        for c in self.children:
            cj = c.to_json()
            if not c.frame and isinstance(cj, dict) and not (merged.keys() & cj.keys()):
                merged.update(cj)
            else:
                frames.append(cj)
        if not frames:
            return merged
        return ([merged] if merged else []) + [frames]

    @classmethod
    def from_json(cls, obj, frame: bool = False) -> BindingNode:
        """Read :meth:`to_json` output, or the bindings JSON shex.js writes."""
        node = cls(frame=frame)
        if isinstance(obj, dict):
            for k, v in obj.items():
                node.vars[k] = term_from_json(v)
        elif isinstance(obj, list):
            for elt in obj:
                if isinstance(elt, list):
                    node.children.extend(cls.from_json(e, frame=True) for e in elt)
                elif isinstance(elt, dict) and not (node.vars.keys() & elt.keys()):
                    node.vars.update((k, term_from_json(v)) for k, v in elt.items())
                else:
                    node.children.append(cls.from_json(elt, frame=False))
        else:
            raise ValueError(f"Not a ShExMap bindings object: {obj!r}")
        return node


# -- term <-> JSON ----------------------------------------------------------------------

def term_to_json(term: Node):
    if isinstance(term, Literal):
        out = {"value": str(term)}
        if term.language:
            out["language"] = term.language
        elif term.datatype is not None and term.datatype != XSD.string:
            out["type"] = str(term.datatype)
        return out
    if isinstance(term, BNode):
        return f"_:{term}"
    return str(term)


def term_from_json(obj) -> Node:
    if isinstance(obj, dict):
        return Literal(obj["value"], lang=obj.get("language"),
                       datatype=URIRef(obj["type"]) if "type" in obj else None)
    if isinstance(obj, str):
        if obj.startswith("_:"):
            return BNode(obj[2:])
        if len(obj) >= 2 and obj[0] == '"':
            return _n3_literal(obj)
        return URIRef(obj)
    raise ValueError(f"Not a ShExMap bound term: {obj!r}")


def _n3_literal(s: str) -> Literal:
    m = re.match(r'^"(.*)"(?:@([A-Za-z\-]+)|\^\^<?([^>]*)>?)?$', s, re.S)
    if not m:
        raise ValueError(f"Not a quoted literal: {s!r}")
    return Literal(m.group(1), lang=m.group(2), datatype=URIRef(m.group(3)) if m.group(3) else None)


def dumps(bindings: BindingNode, **kwargs) -> str:
    return json.dumps(bindings.to_json(), **kwargs)


def loads(text: str) -> BindingNode:
    return BindingNode.from_json(json.loads(text))


# -- prefixes ---------------------------------------------------------------------------

_PREFIX_DECL = re.compile(r'(?im)^\s*PREFIX\s+([A-Za-z0-9_.\-]*):\s*<([^>]*)>')


def shexc_prefixes(shexc: str) -> dict[str, str]:
    """The PREFIX declarations of a ShExC schema; ShExMap variable names use them."""
    return {m.group(1): m.group(2) for m in _PREFIX_DECL.finditer(shexc)}


# -- schema helpers shared with the materializer ------------------------------------------

def map_actions(expr) -> list[ShExJ.SemAct]:
    return [a for a in (getattr(expr, 'semActs', None) or []) if str(a.name) == MAP_EXTENSION]


def cardinality(expr) -> tuple[int, int]:
    """(min, max) with defaults applied; an unbounded max becomes UNBOUNDED_CAP."""
    min_ = 1 if expr.min is None else expr.min
    max_ = 1 if expr.max is None else expr.max
    return min_, (UNBOUNDED_CAP if max_ == -1 else max_)


def is_repeated(expr) -> bool:
    return expr.max is not None and expr.max != 1


def references_shape(se) -> bool:
    """Whether a value expression can bind anything: anything but a node constraint."""
    return se is not None and not isinstance(se, ShExJ.NodeConstraint)


# -- extraction -------------------------------------------------------------------------

class _Extractor:
    def __init__(self, cntxt: Context, prefixes: Mapping[str, str]) -> None:
        self.cntxt = cntxt
        self.prefixes = prefixes
        self.active: set[tuple[Node, int]] = set()

    def satisfies(self, n: Node, se) -> bool:
        """PyShEx's satisfies(), with the parse-tree root that isValid() normally provides."""
        saved = self.cntxt.current_node
        self.cntxt.current_node = ParseNode(satisfies, se, n, self.cntxt)
        try:
            return satisfies(self.cntxt, n, se)
        finally:
            self.cntxt.current_node = saved

    def shape_expr(self, n: Node, se, into: BindingNode) -> None:
        if se is None or se is START:
            se = self.cntxt.schema.start
        if isinstance(se, str):             # a shape label
            se = self.cntxt.shapeExprFor(se)
        if se is None:
            return
        key = (n, id(se))
        if key in self.active:      # recursion: the outer match already collects these
            return
        self.active.add(key)
        try:
            if isinstance(se, ShExJ.ShapeDecl):
                self.shape_expr(n, se.shapeExpr, into)
            elif isinstance(se, ShExJ.Shape):
                self.shape(n, se, into)
            elif isinstance(se, ShExJ.ShapeAnd):
                for part in se.shapeExprs:
                    self.shape_expr(n, part, into)
            elif isinstance(se, ShExJ.ShapeOr):
                for part in se.shapeExprs:
                    if self.satisfies(n, part):
                        self.shape_expr(n, part, into)
                        break
            elif not isinstance(se, (ShExJ.NodeConstraint, ShExJ.ShapeNot, ShExJ.ShapeExternal)):
                resolved = self.cntxt.shapeExprFor(se)
                if resolved is not None and resolved is not se:
                    self.shape_expr(n, resolved, into)
        finally:
            self.active.discard(key)

    def shape(self, n: Node, S: ShExJ.Shape, into: BindingNode) -> None:
        if S.expression is None:
            return
        g = self.cntxt.graph
        available = {('out', t) for t in g.triples((n, None, None))} | \
                    {('in', t) for t in g.triples((None, None, n))}
        assignment = self._assign(S.expression, available)
        for item in assignment or []:
            self._bind(*item, into)

    def _candidates(self, tc: ShExJ.TripleConstraint, available) -> list:
        direction = 'in' if tc.inverse else 'out'
        pred = URIRef(str(tc.predicate))
        found = []
        for d, t in available:
            if d != direction or t[1] != pred:
                continue
            value = t[0] if tc.inverse else t[2]
            if tc.valueExpr is None or self.satisfies(value, tc.valueExpr):
                found.append((d, t))
        return sorted(found, key=lambda dt: (dt[1][0] if tc.inverse else dt[1][2]).n3())

    def _assign(self, expr, available: set):
        """Assign triples to triple constraints: a list of (tc, triples, group_frame) or None."""
        if isinstance(expr, str):           # an inclusion: &label
            expr = self.cntxt.tripleExprFor(expr)
            if expr is None:
                return None
        if isinstance(expr, ShExJ.TripleConstraint):
            min_, max_ = cardinality(expr)
            taken = self._candidates(expr, available)[:max_]
            if len(taken) < min_:
                return None
            available.difference_update(taken)
            return [(expr, [t for _, t in taken], False)]
        # EachOf / OneOf, possibly repeated as a group
        min_, max_ = cardinality(expr)
        repeated = is_repeated(expr)
        result, count = [], 0
        while count < max_:
            trial = set(available)
            one = self._assign_once(expr, trial)
            if one is None:
                break
            progressed = trial != available
            if not progressed and count >= min_:
                break
            available.intersection_update(trial)
            result.extend([(None, one, True)] if repeated else one)
            count += 1
            if not progressed:          # an iteration that matched nothing would repeat forever
                break
        return result if count >= min_ else None

    def _assign_once(self, expr, available: set):
        if isinstance(expr, ShExJ.EachOf):
            out = []
            for sub in expr.expressions:
                part = self._assign(sub, available)
                if part is None:
                    return None
                out.extend(part)
            return out
        if isinstance(expr, ShExJ.OneOf):
            for sub in expr.expressions:
                trial = set(available)
                part = self._assign(sub, trial)
                if part is not None:
                    available.intersection_update(trial)
                    return part
            return None
        raise NotImplementedError(f"Unexpected triple expression {type(expr).__name__}")

    def _bind(self, tc, triples, group_frame: bool, into: BindingNode) -> None:
        if tc is None:                       # one iteration of a repeated group
            frame = BindingNode(frame=True)
            for item in triples:
                self._bind(*item, frame)
            if not frame.is_empty():
                into.children.append(frame)
            return
        per_value = group_frame or is_repeated(tc)
        for t in triples:
            value = t[0] if tc.inverse else t[2]
            lifted = self.lift(tc, value)
            child = None
            if references_shape(tc.valueExpr):
                child = BindingNode(frame=per_value)
                self.shape_expr(value, tc.valueExpr, child)
            if child is not None:
                child.vars = {**lifted, **child.vars}
                if not child.is_empty():
                    into.children.append(child)
            elif per_value:
                if lifted:
                    into.children.append(BindingNode(vars=lifted, frame=True))
            else:
                into.vars.update(lifted)

    def lift(self, tc, value) -> dict[str, Node]:
        bound: dict[str, Node] = {}
        for act in map_actions(tc):
            code = str(act.code or '')
            if functions.is_function_call(code):
                bound.update(functions.lift(code, value, self.prefixes))
            else:
                bound[functions.expand_variable(code, self.prefixes)] = value
        return bound


class MapValidationError(ValueError):
    """The input data does not conform to the input schema, so nothing can be bound."""


def bind(graph: Graph, schema: str | ShExJ.Schema, focus: str | Node, start=None,
         prefixes: Mapping[str, str] | None = None) -> BindingNode:
    """Validate ``focus`` in ``graph`` against ``schema`` and collect its ShExMap bindings.

    :param graph: input RDF
    :param schema: input schema, as ShExC text or a parsed ShExJ schema
    :param focus: the node to start from
    :param start: shape label to validate against; defaults to the schema's start
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :raises MapValidationError: when ``focus`` does not conform
    """
    from pyshex.shape_expressions_language.p5_2_validation_definition import isValid
    from pyshex.shapemap_structure_and_language.p3_shapemap_structure import FixedShapeMap, ShapeAssociation
    from pyshex.shexmap.semact import register
    from pyshex.utils.schema_loader import SchemaLoader

    register()
    if isinstance(schema, str):
        prefixes = {**shexc_prefixes(schema), **(prefixes or {})}
        schema = SchemaLoader().loads(schema)
    prefixes = dict(prefixes or {})
    if not isinstance(focus, (URIRef, BNode)):
        focus = BNode(focus[2:]) if str(focus).startswith('_:') else URIRef(str(focus))
    label = START if start is None or start is START else ShExJ.IRIREF(str(start))
    cntxt = Context(graph, schema)
    cntxt.shexmap_prefixes = prefixes
    shape_map = FixedShapeMap()
    shape_map.add(ShapeAssociation(focus, label))
    ok, reasons = isValid(cntxt, shape_map)
    if not ok:
        raise MapValidationError(f"{focus} does not conform: " + "\n".join(reasons))
    cntxt = Context(graph, schema)
    root = BindingNode()
    se = cntxt.shapeExprFor(ShExJ.IRIREF(str(start))) if start is not None else schema.start
    _Extractor(cntxt, prefixes).shape_expr(focus, se, root)
    return root
