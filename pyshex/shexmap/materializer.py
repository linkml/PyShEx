"""Build RDF that conforms to an output schema from ShExMap bindings.

The output schema is walked from its start (or a given) shape.  For each triple constraint:

* with ``%Map:{ var %}`` -- emit the variable's value (or what a function builds from
  bindings); a repeated constraint emits one triple per available value;
* whose value set holds exactly one value, e.g. ``a [fhir:Observation]?`` -- emit that value;
* whose value is a shape -- create a blank node and materialize the shape on it, as often
  as the cardinality allows and bindings remain;
* anything else cannot be materialized: fine when optional, a failure when required.

A failure propagates up to the nearest optional or repeated construct, which is then
rolled back, so a partly built subtree never reaches the output.  ``OneOf`` and
``ShapeOr`` take the first alternative that succeeds.

Bindings are served by a :class:`Binder`: a variable bound only once in the whole tree is
shared everywhere; other values are consumed in order, and each repetition of a repeated
construct draws its values from a single frame of the bindings (see
:mod:`pyshex.shexmap.bindings`).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions
from pyshex.shexmap.bindings import (BindingNode, cardinality, is_repeated, map_actions, references_shape,
                                     shexc_prefixes)

MAX_DEPTH = 64


class MaterializationError(ValueError):
    """The output schema cannot be satisfied from the bindings."""


@dataclass(frozen=True)
class _Record:
    vars: dict
    frames: tuple[int, ...]     # ids of the frames this record lies in, outermost first


class Binder:
    """Serve binding values to the materializer."""

    def __init__(self, bindings: BindingNode, static_vars: Mapping[str, Node] | None = None) -> None:
        self.records: list[_Record] = []
        self._flatten(bindings, (0,), [0])
        counts: dict[str, int] = {}
        for r in self.records:
            for k in r.vars:
                counts[k] = counts.get(k, 0) + 1
        # A value bound once, outside every frame (e.g. a patient's name above repeated
        # observations), is shared by all of them, as shex.js copies it into each frame.
        self.shared = {k: v for r in self.records if len(r.frames) == 1
                       for k, v in r.vars.items() if counts[k] == 1}
        self.shared.update(static_vars or {})
        self.consumed: set[tuple[int, str]] = set()
        self.pins: list[int | None] = []     # frame each open repetition draws from; None until chosen
        self.used = 0                        # number of values consumed so far

    def _flatten(self, node: BindingNode, frames: tuple[int, ...], next_id: list[int]) -> None:
        if node.frame:
            next_id[0] += 1
            frames = frames + (next_id[0],)
        if node.vars:
            self.records.append(_Record(node.vars, frames))
        for c in node.children:
            self._flatten(c, frames, next_id)

    def get(self, var: str) -> Node | None:
        if var in self.shared:
            return self.shared[var]
        scope = next((p for p in reversed(self.pins) if p is not None), None)
        for i, r in enumerate(self.records):
            if var in r.vars and (i, var) not in self.consumed and (scope is None or scope in r.frames):
                self.consumed.add((i, var))
                self.used += 1
                if self.pins and self.pins[-1] is None:
                    # the first value a repetition takes decides which frame it draws from
                    self.pins[-1] = r.frames[-1]
                return r.vars[var]
        return None

    def begin_repetition(self) -> None:
        self.pins.append(None)

    def end_repetition(self) -> None:
        self.pins.pop()

    def snapshot(self):
        return set(self.consumed), list(self.pins), self.used

    def restore(self, snap) -> None:
        consumed, pins, used = snap
        self.consumed, self.pins, self.used = set(consumed), list(pins), used


class _Materializer:
    def __init__(self, schema: ShExJ.Schema, binder: Binder, prefixes: Mapping[str, str]) -> None:
        self.cntxt = Context(None, schema)
        self.binder = binder
        self.prefixes = prefixes
        self.triples: list[tuple[Node, Node, Node]] = []
        self.depth = 0

    # transactions: roll back emitted triples and consumed bindings together
    def _snap(self):
        return len(self.triples), self.binder.snapshot()

    def _restore(self, snap) -> None:
        del self.triples[snap[0]:]
        self.binder.restore(snap[1])

    def emit(self, s: Node, p: Node, o: Node) -> None:
        self.triples.append((s, p, o))

    # shape expressions ---------------------------------------------------------------
    def shape_expr(self, node: Node, se) -> bool:
        if isinstance(se, str):
            resolved = self.cntxt.shapeExprFor(se)
            if resolved is None:
                raise MaterializationError(f"Shape {se} is not defined in the output schema")
            se = resolved
        if self.depth > MAX_DEPTH:
            return False
        self.depth += 1
        try:
            if isinstance(se, ShExJ.ShapeDecl):
                return self.shape_expr(node, se.shapeExpr)
            if isinstance(se, ShExJ.Shape):
                return se.expression is None or self.triple_expr(node, se.expression)
            if isinstance(se, ShExJ.ShapeAnd):
                return all(self.shape_expr(node, part) for part in se.shapeExprs)
            if isinstance(se, ShExJ.ShapeOr):
                for part in se.shapeExprs:
                    snap = self._snap()
                    if self.shape_expr(node, part):
                        return True
                    self._restore(snap)
                return False
            return True     # NodeConstraint, ShapeNot, ShapeExternal: nothing to emit
        finally:
            self.depth -= 1

    # triple expressions --------------------------------------------------------------
    def triple_expr(self, node: Node, te) -> bool:
        if isinstance(te, str):
            resolved = self.cntxt.tripleExprFor(te)
            if resolved is None:
                raise MaterializationError(f"Triple expression {te} is not defined in the output schema")
            te = resolved
        if isinstance(te, ShExJ.TripleConstraint):
            return self.triple_constraint(node, te)
        return self._repeat(te, lambda: self._group_once(node, te), repeated=is_repeated(te))

    def _group_once(self, node: Node, te) -> bool:
        if isinstance(te, ShExJ.EachOf):
            return all(self.triple_expr(node, sub) for sub in te.expressions)
        for sub in te.expressions:      # OneOf
            snap = self._snap()
            if self.triple_expr(node, sub):
                return True
            self._restore(snap)
        return False

    def _repeat(self, expr, once, repeated: bool) -> bool:
        """Run ``once`` as often as expr's cardinality allows and it keeps consuming bindings."""
        min_, max_ = cardinality(expr)
        count = 0
        while count < max_:
            snap = self._snap()
            used = self.binder.used
            if repeated:
                self.binder.begin_repetition()
            try:
                ok = once()
            finally:
                if repeated:
                    self.binder.end_repetition()
            consumed = self.binder.used > used
            if not ok or (not consumed and count >= min_):
                self._restore(snap)
                break
            count += 1
            if not consumed:            # more of the same would add nothing new
                break
        return count >= min_

    def triple_constraint(self, node: Node, tc: ShExJ.TripleConstraint) -> bool:
        pred = URIRef(str(tc.predicate))

        def link(value: Node) -> None:
            if tc.inverse:
                self.emit(value, pred, node)
            else:
                self.emit(node, pred, value)

        acts = map_actions(tc)
        if acts:
            def once() -> bool:
                values = [v for v in (self.lower(str(a.code or '')) for a in acts) if v is not None]
                for v in values:
                    link(v)
                return bool(values)
            return self._repeat(tc, once, repeated=is_repeated(tc))

        constant = _single_value(tc.valueExpr)
        if constant is not None:
            link(constant)
            return True

        if references_shape(tc.valueExpr):
            def once() -> bool:
                bnode = BNode()
                if not self.shape_expr(bnode, tc.valueExpr):
                    return False
                link(bnode)
                return True
            return self._repeat(tc, once, repeated=is_repeated(tc))

        return cardinality(tc)[0] == 0    # nothing to build a value from

    def lower(self, code: str) -> Node | None:
        if functions.is_function_call(code):
            return functions.lower(code, self.binder.get, self.prefixes)
        return self.binder.get(functions.expand_variable(code, self.prefixes))


def _single_value(value_expr) -> Node | None:
    if not isinstance(value_expr, ShExJ.NodeConstraint) or not value_expr.values or len(value_expr.values) != 1:
        return None
    v = value_expr.values[0]
    if isinstance(v, ShExJ.ObjectLiteral):
        return Literal(v.value, lang=v.language, datatype=URIRef(v.type) if v.type else None)
    if isinstance(v, str):
        return URIRef(str(v))
    return None     # stems, ranges and languages do not name one value


def materialize(schema: str | ShExJ.Schema, bindings: BindingNode, root: str | Node, start=None,
                static_vars: Mapping[str, Node] | None = None, prefixes: Mapping[str, str] | None = None,
                graph: Graph | None = None) -> Graph:
    """Materialize ``root`` as an instance of the output schema from ``bindings``.

    :param schema: output schema, as ShExC text or a parsed ShExJ schema
    :param bindings: from :func:`pyshex.shexmap.bind` or :func:`pyshex.shexmap.bindings.loads`
    :param root: the node to build; a ``_:`` string makes a blank node
    :param start: shape label to build; defaults to the schema's start
    :param static_vars: extra variable values, shared everywhere (shex.js ``staticVars``)
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :param graph: graph to add to; a new one by default
    :raises MaterializationError: when the start shape cannot be built
    """
    from pyshex.utils.schema_loader import SchemaLoader

    if isinstance(schema, str):
        prefixes = {**shexc_prefixes(schema), **(prefixes or {})}
        schema = SchemaLoader().loads(schema)
    if not isinstance(root, (URIRef, BNode)):
        root = BNode(root[2:]) if str(root).startswith('_:') else URIRef(str(root))
    m = _Materializer(schema, Binder(bindings, static_vars), dict(prefixes or {}))
    se = schema.start if start is None or start is START else ShExJ.IRIREF(str(start))
    if se is None:
        raise MaterializationError("The output schema has no start shape; name one with start=")
    if not m.shape_expr(root, se):
        raise MaterializationError(f"Could not materialize {root} from the bindings")
    graph = graph if graph is not None else Graph()
    for prefix, ns in m.prefixes.items():
        graph.bind(prefix, ns, override=False)
    for t in m.triples:
        graph.add(t)
    return graph
