"""Collect ShExMap bindings from RDF that conforms to an input schema.

**Binding trees** use the structure shex.js prints and reads, with rdflib terms as values:
an object maps variable IRIs to terms, and a list is a sequence whose elements are
objects or nested lists.  A repeated match (a triple constraint with max > 1, or one
iteration of a repeated group) contributes one element to a list, so everything bound
from one reading of a blood pressure stays together.  :class:`Bindings` wraps a tree,
and :func:`dumps`/:func:`loads` convert to and from shex.js's JSON.

**Collecting** happens after validation succeeds.  PyShEx checks that *some* partition
of each node's neighbourhood satisfies the schema but does not say which, so the
triples are partitioned again here, by an exhaustive search in schema order (larger
matches first).  When several partitions -- or several ways to satisfy nested shapes --
lead to different bindings, the input schema is ambiguous for mapping: :func:`bind`
returns the first and records how many there were, :func:`bind_all` returns them all,
and ``strict=True`` turns ambiguity into an error.

EXTENDS is followed: a shape's neighbourhood is shared between its own expression and
the shapes it extends, and a reference to a shape with extensions binds through the
most specific extension the node satisfies.  Inverse triple constraints (``^p``) bind
the subject of the matched triple.
"""
from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef, XSD
from rdflib.term import Node

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_3_shape_expressions import _non_abstract_descendants, satisfies
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions

MAP_EXTENSION = "http://shex.io/extensions/Map/#"

UNBOUNDED_CAP = 50           # never expand "*" further than this (matches shex.js)
MAX_ALTERNATIVES = 20        # distinct binding trees to collect before giving up counting
MAX_PARTITIONS = 10_000      # partitions of one neighbourhood to try


class MapValidationError(ValueError):
    """The input data does not conform to the input schema, so nothing can be bound."""


class AmbiguousBindingsError(MapValidationError):
    """The input conforms in more than one way, and the ways bind different values."""

    def __init__(self, message: str, alternatives: list[Bindings]) -> None:
        super().__init__(message)
        self.alternatives = alternatives


# -- binding trees ----------------------------------------------------------------------

class Bindings:
    """A binding tree (see module docstring), and how many distinct ones the input allowed."""

    def __init__(self, tree, alternatives: int = 1) -> None:
        self.tree = tree
        self.alternatives = alternatives

    @property
    def ambiguous(self) -> bool:
        return self.alternatives > 1

    def to_json(self):
        return _map_tree(self.tree, term_to_json)

    @classmethod
    def from_json(cls, obj) -> Bindings:
        return cls(_map_tree(obj, term_from_json))

    def frames(self) -> list[dict[str, Node]]:
        """The tree flattened to the frame sequence materialization reads (see :func:`normalize`)."""
        return normalize(self.tree)

    def variables(self) -> set[str]:
        return {k for frame in self.frames() for k in frame}

    def __eq__(self, other) -> bool:
        return isinstance(other, Bindings) and self.to_json() == other.to_json()

    def __repr__(self) -> str:
        return f"Bindings({json.dumps(self.to_json())[:200]}, alternatives={self.alternatives})"


def _map_tree(tree, fn):
    if isinstance(tree, dict):
        return {k: fn(v) for k, v in tree.items()}
    if isinstance(tree, list):
        return [_map_tree(e, fn) for e in tree]
    raise ValueError(f"Not a ShExMap binding tree: {tree!r}")


def normalize(tree) -> list[dict[str, Node]]:
    """Flatten a binding tree to a sequence of frames, as shex.js's ThreadedMaterializer does.

    A binding whose variable occurs once under a list level (a patient's name beside the
    list of their readings) is copied into every frame the sibling lists produce."""
    def walk(node):
        if not isinstance(node, list):
            return [dict(node)], True, {k: 1 for k in node}
        kids = [walk(k) for k in node]
        counts: dict[str, int] = {}
        for _, _, c in kids:
            for k, n in c.items():
                counts[k] = counts.get(k, 0) + n
        if all(leaf for _, leaf, _ in kids):    # a plain sequence of frames
            return [f for fs, _, _ in kids for f in fs], False, counts
        shared: dict[str, Node] = {}
        ordered = []
        for frames, leaf, _ in kids:
            if leaf:
                rest = {}
                for k, v in frames[0].items():
                    (shared if counts[k] == 1 else rest)[k] = v
                if rest:
                    ordered.append(([rest], True))
            else:
                ordered.append((frames, False))
        out = []
        for frames, leaf in ordered:
            out.extend(f if leaf else {**shared, **f} for f in frames)
        return out, False, counts
    return walk(tree)[0]


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


def dumps(bindings: Bindings, **kwargs) -> str:
    return json.dumps(bindings.to_json(), **kwargs)


def loads(text: str) -> Bindings:
    return Bindings.from_json(json.loads(text))


# -- prefixes and schema helpers (shared with the materializer) --------------------------

_PREFIX_DECL = re.compile(r'(?im)^\s*PREFIX\s+([A-Za-z0-9_.\-]*):\s*<([^>]*)>')


def shexc_prefixes(shexc: str) -> dict[str, str]:
    """The PREFIX declarations of a ShExC schema; ShExMap variable names use them."""
    return {m.group(1): m.group(2) for m in _PREFIX_DECL.finditer(shexc)}


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


def declaration_of(cntxt: Context, label):
    """The declaration (ShapeDecl, or a labelled shape expression) for a shape label."""
    return cntxt.shapeExprFor(label)


def expression_of(decl):
    return decl.shapeExpr if isinstance(decl, ShExJ.ShapeDecl) else decl


def extension_candidates(cntxt: Context, decl) -> list:
    """What satisfying ``decl`` can mean, most specific first: its non-abstract
    extensions (deepest first), then the declaration itself unless it is abstract."""
    if getattr(decl, 'id', None) is None:
        return [decl]
    found = list(reversed(_non_abstract_descendants(cntxt, decl)))
    if not getattr(decl, 'abstract', None):
        found.append(decl)
    return found


def shape_parts(cntxt: Context, S: ShExJ.Shape, seen: set | None = None) -> list[ShExJ.Shape]:
    """The shapes whose triple expressions share a node's neighbourhood when it matches
    ``S``: those of everything ``S`` EXTENDS (transitively), then ``S`` itself."""
    seen = seen if seen is not None else set()
    parts: list[ShExJ.Shape] = []
    for base in getattr(S, 'extends', None) or []:
        if str(base) in seen:
            continue
        seen.add(str(base))
        for shape in _shapes_in(expression_of(declaration_of(cntxt, base))):
            parts.extend(shape_parts(cntxt, shape, seen))
    parts.append(S)
    return parts


def _shapes_in(se) -> list[ShExJ.Shape]:
    if isinstance(se, ShExJ.Shape):
        return [se]
    if isinstance(se, ShExJ.ShapeAnd):
        return [s for part in se.shapeExprs for s in _shapes_in(part)]
    return []


def triple_constraints(se, cntxt: Context | None = None) -> Iterator[ShExJ.TripleConstraint]:
    """Every triple constraint reachable from a shape or triple expression."""
    stack, seen = [se], set()
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, ShExJ.TripleConstraint):
            yield e
            stack.append(e.valueExpr)
        elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
            stack.extend(e.expressions)
        elif isinstance(e, ShExJ.Shape):
            stack.append(e.expression)
        elif isinstance(e, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            stack.extend(e.shapeExprs)
        elif isinstance(e, (ShExJ.ShapeNot, ShExJ.ShapeDecl)):
            stack.append(e.shapeExpr)
        elif isinstance(e, str) and cntxt is not None:
            stack.append(cntxt.tripleExprFor(e))


# -- extraction ---------------------------------------------------------------------------

@dataclass
class _Record:
    """Bindings made while matching one node: its own variables and nested matches."""
    vars: dict[str, Node] = field(default_factory=dict)
    children: list[_Record] = field(default_factory=list)
    frame: bool = False

    def merged(self, other: _Record) -> _Record:
        return _Record({**self.vars, **other.vars}, self.children + other.children, self.frame)

    def empty(self) -> bool:
        return not self.vars and all(c.empty() for c in self.children)

    def tree(self):
        """Non-repeated nested matches merge into this object; repeated ones become a list."""
        merged = dict(self.vars)
        frames = []
        for c in self.children:
            ct = c.tree()
            if not c.frame and isinstance(ct, dict) and not (merged.keys() & ct.keys()):
                merged.update(ct)
            else:
                frames.append(ct)
        if not frames:
            return merged
        return ([merged] if merged else []) + [frames]


def _product(alternatives: list[list[_Record]], limit: int) -> list[_Record]:
    out: list[_Record] = []
    for combo in itertools.product(*alternatives):
        rec = _Record()
        for r in combo:
            rec = rec.merged(r)
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def _dedupe(records: Iterable[_Record], limit: int) -> list[_Record]:
    seen, out = set(), []
    for r in records:
        key = json.dumps(_map_tree(r.tree(), lambda t: t.n3()), sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(r)
            if len(out) >= limit:
                break
    return out


class _Extractor:
    def __init__(self, cntxt: Context, prefixes: Mapping[str, str], limit: int = MAX_ALTERNATIVES) -> None:
        self.cntxt = cntxt
        self.prefixes = prefixes
        self.limit = limit
        self.active: set[tuple[Node, int]] = set()
        self._sat_cache: dict[tuple[Node, int], bool] = {}

    def satisfies(self, n: Node, se) -> bool:
        """PyShEx's satisfies(), with the parse-tree root isValid() normally provides."""
        key = (n, id(se))
        if key not in self._sat_cache:
            saved = self.cntxt.current_node
            self.cntxt.current_node = ParseNode(satisfies, se, n, self.cntxt)
            try:
                self._sat_cache[key] = satisfies(self.cntxt, n, se)
            finally:
                self.cntxt.current_node = saved
        return self._sat_cache[key]

    # shape expressions: each returns the alternative records for node n
    def shape_expr(self, n: Node, se) -> list[_Record]:
        if se is None or se is START:
            se = self.cntxt.schema.start
        if isinstance(se, str):                 # a reference: bind through the most specific match
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                return [_Record()]
            for candidate in extension_candidates(self.cntxt, decl):
                if candidate is decl or self.satisfies(n, candidate):
                    return self._guarded(n, expression_of(candidate))
            return [_Record()]
        return self._guarded(n, se)

    def _guarded(self, n: Node, se) -> list[_Record]:
        key = (n, id(se))
        if key in self.active:      # recursion: the outer match already collects these
            return [_Record()]
        self.active.add(key)
        try:
            return self._shape_expr(n, se)
        finally:
            self.active.discard(key)

    def _shape_expr(self, n: Node, se) -> list[_Record]:
        if isinstance(se, ShExJ.ShapeDecl):
            return self.shape_expr(n, se.shapeExpr)
        if isinstance(se, ShExJ.Shape):
            return self.shape(n, se)
        if isinstance(se, ShExJ.ShapeAnd):
            return _dedupe(_product([self.shape_expr(n, p) for p in se.shapeExprs], self.limit), self.limit)
        if isinstance(se, ShExJ.ShapeOr):
            for part in se.shapeExprs:
                if self.satisfies(n, part):
                    return self.shape_expr(n, part)
            return [_Record()]
        return [_Record()]      # NodeConstraint, ShapeNot, ShapeExternal bind nothing

    # shapes: partition the neighbourhood, then bind each partition
    def shape(self, n: Node, S: ShExJ.Shape) -> list[_Record]:
        parts = shape_parts(self.cntxt, S)
        tcs = [tc for p in parts for tc in self._own_tcs(p)]
        keys = {(URIRef(str(tc.predicate)), bool(tc.inverse)) for tc in tcs}
        g = self.cntxt.graph
        matchables = frozenset(
            [('out', t) for t in g.triples((n, None, None)) if (t[1], False) in keys] +
            [('in', t) for t in g.triples((None, None, n)) if (t[1], True) in keys])
        extras = {URIRef(str(e)) for p in parts for e in (getattr(p, 'extra', None) or [])}

        results: list[_Record] = []
        tried = 0
        for items, rest in self._parts(n, [p.expression for p in parts if p.expression is not None], matchables):
            tried += 1
            if tried > MAX_PARTITIONS:
                break
            if not self._valid_remainder(n, rest, extras, tcs):
                continue
            results.extend(self._bind_items(items))
            results = _dedupe(results, self.limit)
            if len(results) >= self.limit:
                break
        return results or [_Record()]

    def _own_tcs(self, S: ShExJ.Shape) -> list[ShExJ.TripleConstraint]:
        """Triple constraints of S's own expression, not of the shapes nested in them."""
        out, stack = [], [S.expression]
        while stack:
            e = stack.pop()
            if isinstance(e, ShExJ.TripleConstraint):
                out.append(e)
            elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
                stack.extend(e.expressions)
            elif isinstance(e, str):
                stack.append(self.cntxt.tripleExprFor(e))
        return out

    def _valid_remainder(self, n: Node, rest, extras, tcs) -> bool:
        for d, t in rest:
            if d != 'out' or t[1] not in extras:
                return False
            # EXTRA may only absorb a triple that no constraint on its predicate accepts
            if any(URIRef(str(tc.predicate)) == t[1] and not tc.inverse and
                   (tc.valueExpr is None or self.satisfies(t[2], tc.valueExpr)) for tc in tcs):
                return False
        return True

    def _parts(self, n: Node, exprs: list, available: frozenset):
        """Partitions of ``available`` among a sequence of triple expressions."""
        if not exprs:
            yield [], available
            return
        for items, rest in self._match(n, exprs[0], available):
            for more, rest2 in self._parts(n, exprs[1:], rest):
                yield items + more, rest2

    def _match(self, n: Node, expr, available: frozenset):
        """Ways ``expr`` can match some of ``available``: (items, remaining) pairs, greediest
        first.  Items are ('tc', tc, triple) or ('group', items) for a repeated group's iteration."""
        if isinstance(expr, str):               # an inclusion: &label
            expr = self.cntxt.tripleExprFor(expr)
        if isinstance(expr, ShExJ.TripleConstraint):
            min_, max_ = cardinality(expr)
            direction = 'in' if expr.inverse else 'out'
            pred = URIRef(str(expr.predicate))
            candidates = sorted(
                (dt for dt in available if dt[0] == direction and dt[1][1] == pred
                 and (expr.valueExpr is None or self.satisfies(self._value(expr, dt[1]), expr.valueExpr))),
                key=lambda dt: self._value(expr, dt[1]).n3())
            for k in range(min(max_, len(candidates)), min_ - 1, -1):
                for combo in itertools.combinations(candidates, k):
                    yield [('tc', expr, t) for _, t in combo], available - frozenset(combo)
            return
        min_, max_ = cardinality(expr)
        repeated = is_repeated(expr)
        yield from self._repeat(n, expr, available, 0, min_, max_, repeated)

    def _repeat(self, n: Node, expr, available: frozenset, count: int, min_: int, max_: int, repeated: bool):
        if count < max_:
            for one, rest in self._once(n, expr, available):
                if rest == available and count >= min_:
                    continue            # an iteration that matches nothing adds nothing
                wrapped = [('group', one)] if repeated else one
                if rest == available:   # matched nothing but is required: count it once
                    yield wrapped, rest
                    continue
                for more, rest2 in self._repeat(n, expr, rest, count + 1, min_, max_, repeated):
                    yield wrapped + more, rest2
        if count >= min_:
            yield [], available

    def _once(self, n: Node, expr, available: frozenset):
        if isinstance(expr, ShExJ.EachOf):
            yield from self._parts(n, list(expr.expressions), available)
        elif isinstance(expr, ShExJ.OneOf):
            for sub in expr.expressions:
                yield from self._match(n, sub, available)
        else:
            raise NotImplementedError(f"Unexpected triple expression {type(expr).__name__}")

    @staticmethod
    def _value(tc: ShExJ.TripleConstraint, t) -> Node:
        return t[0] if tc.inverse else t[2]

    def _bind_items(self, items) -> list[_Record]:
        """Alternative records for one partition's items."""
        alternatives: list[list[_Record]] = []
        for item in items:
            if item[0] == 'group':          # one iteration of a repeated group: one frame
                opts = []
                for r in self._bind_items(item[1]):
                    iteration = _Record(r.vars, r.children, True)
                    opts.append(_Record(children=[iteration]) if not iteration.empty() else _Record())
                alternatives.append(opts or [_Record()])
                continue
            _, tc, t = item
            value = self._value(tc, t)
            lifted = self.lift(tc, value)
            per_value = is_repeated(tc)
            if references_shape(tc.valueExpr):
                opts = []
                for sub in self.shape_expr(value, tc.valueExpr):
                    child = _Record({**lifted, **sub.vars}, sub.children, per_value)
                    opts.append(_Record(children=[child]) if not child.empty() else _Record())
                alternatives.append(opts)
            elif per_value:
                alternatives.append([_Record(children=[_Record(lifted, frame=True)]) if lifted else _Record()])
            else:
                alternatives.append([_Record(lifted)])
        return _product(alternatives, self.limit)

    def lift(self, tc, value) -> dict[str, Node]:
        bound: dict[str, Node] = {}
        for act in map_actions(tc):
            code = str(act.code or '')
            if functions.is_function_call(code):
                bound.update(functions.lift(code, value, self.prefixes))
            else:
                bound[functions.expand_variable(code, self.prefixes)] = value
        return bound


def _prepare(schema, prefixes):
    from pyshex.utils.schema_loader import SchemaLoader
    if isinstance(schema, str):
        prefixes = {**shexc_prefixes(schema), **(prefixes or {})}
        schema = SchemaLoader().loads(schema)
        if schema is None:
            raise MapValidationError("The schema does not parse")
    return schema, dict(prefixes or {})


def _node(term) -> Node:
    if isinstance(term, (URIRef, BNode, Literal)):
        return term
    return BNode(str(term)[2:]) if str(term).startswith('_:') else URIRef(str(term))


def bind_all(graph: Graph, schema: str | ShExJ.Schema, focus: str | Node, start=None,
             prefixes: Mapping[str, str] | None = None, limit: int = MAX_ALTERNATIVES) -> list[Bindings]:
    """Validate ``focus`` and return every distinct binding tree the input allows (up to ``limit``).

    :param graph: input RDF
    :param schema: input schema, as ShExC text or a parsed ShExJ schema
    :param focus: the node to start from (``_:label`` for a blank node)
    :param start: shape label to validate against; defaults to the schema's start
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :raises MapValidationError: when ``focus`` does not conform
    """
    from pyshex.shape_expressions_language.p5_2_validation_definition import isValid
    from pyshex.shapemap_structure_and_language.p3_shapemap_structure import FixedShapeMap, ShapeAssociation
    from pyshex.shexmap.semact import register

    register()
    schema, prefixes = _prepare(schema, prefixes)
    focus = _node(focus)
    label = START if start is None or start is START else ShExJ.IRIREF(str(start))
    cntxt = Context(graph, schema)
    cntxt.shexmap_prefixes = prefixes
    shape_map = FixedShapeMap()
    shape_map.add(ShapeAssociation(focus, label))
    ok, reasons = isValid(cntxt, shape_map)
    if not ok:
        raise MapValidationError(f"{focus} does not conform: " + "\n".join(reasons))
    extractor = _Extractor(Context(graph, schema), prefixes, limit)
    records = extractor.shape_expr(focus, label if label is not START else START)
    trees = [r.tree() for r in _dedupe(records, limit)]
    return [Bindings(t, alternatives=len(trees)) for t in trees]


def bind(graph: Graph, schema: str | ShExJ.Schema, focus: str | Node, start=None,
         prefixes: Mapping[str, str] | None = None, strict: bool = False) -> Bindings:
    """Validate ``focus`` in ``graph`` against ``schema`` and collect its ShExMap bindings.

    When the input conforms in several ways that bind differently, the first (in schema
    order, larger matches first) is returned and ``.alternatives`` says how many there
    were; with ``strict=True`` an :class:`AmbiguousBindingsError` is raised instead.
    """
    found = bind_all(graph, schema, focus, start=start, prefixes=prefixes)
    if strict and len(found) > 1:
        raise AmbiguousBindingsError(
            f"{focus} matches the input schema in {len(found)} ways that bind different values", found)
    return found[0]
