"""Collect ShExMap bindings from RDF that conforms to an input schema.

**Binding trees** use the structure shex.js prints and reads, with rdflib terms as values.
A *scope* (what one node's match binds) is an object mapping variable IRIs to terms, or,
when the match has repeated parts, an array whose first element is that object (possibly
empty) and whose other elements are *lists*; a list has one element per iteration of a
repeated constraint or group, each element a scope, so everything bound from one reading
of a blood pressure stays together.  A list's elements are uniform: all objects, or all
arrays (a lone object among arrays is written as ``[object]``), so that a reader never has
to guess whether an array is a scope or a list.  Every repeated constraint or group of the
shape gets its list, in schema order, empty when nothing matched, so a list's position
says which expression it came from whatever the data.  A non-repeated nested shape merges
into the scope that matched it.  An element made by a repeated *shape-valued* constraint also
records the node the nested shape matched under the reserved key ``"@node"``
(:data:`NODE_KEY`; the subject for an inverse constraint).  It is not a variable:
:func:`normalize` leaves it out of the frames and no output constraint can read it.  It
says which input node an iteration came from, which is what tells two groups apart when
their bindings are alike.  :class:`Bindings` wraps a tree, and :func:`dumps`/:func:`loads`
convert to and from shex.js's JSON.

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
import math
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef, XSD
from rdflib.term import Node

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_3_shape_expressions import _non_abstract_descendants, satisfies
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions

MAP_EXTENSION = "http://shex.io/extensions/Map/#"

NODE_KEY = "@node"           # in an iteration's bindings: the node the nested shape matched

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
    """A binding tree (see module docstring), how many distinct ones the input allowed, and
    the triples the schema matched to make it (``matched``: the subgraph it selected)."""

    def __init__(self, tree, alternatives: int = 1, matched: frozenset = frozenset()) -> None:
        self.tree = tree
        self.alternatives = alternatives
        self.matched = matched

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
            own = {k: v for k, v in node.items() if k != NODE_KEY}
            return [own], True, {k: 1 for k in own}
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
        if not out and shared:      # a scope whose lists are all empty still has its own bindings
            out.append(shared)
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


def cardinality(expr) -> tuple[int, float]:
    """(min, max) with defaults applied; an unbounded max is ``math.inf``.

    Nothing caps a ``*`` or ``+`` here: how many triples a constraint may take is decided
    by the neighbourhood, as it is in validation (shex.js validates without a cap too)."""
    min_ = 1 if expr.min is None else expr.min
    max_ = 1 if expr.max is None else expr.max
    return min_, (math.inf if max_ == -1 else max_)


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
    """One scope: the bindings made while matching one node, one list of iteration records
    per repeated constraint or group that matched under it, and the triples matched here."""
    vars: dict[str, Node] = field(default_factory=dict)
    lists: list[list[_Record]] = field(default_factory=list)
    triples: set = field(default_factory=set)

    def merged(self, other: _Record) -> _Record:
        return _Record({**self.vars, **other.vars}, self.lists + other.lists, self.triples | other.triples)

    def all_triples(self) -> frozenset:
        """The triples matched here and in every nested scope."""
        out = set(self.triples)
        for lst in self.lists:
            for r in lst:
                out |= r.all_triples()
        return frozenset(out)

    def empty(self) -> bool:
        return not (self.vars.keys() - {NODE_KEY}) and all(r.empty() for lst in self.lists for r in lst)

    def tree(self):
        """The scope as a binding tree: the object alone, or ``[object, list, ...]``, each
        list's elements uniform (all objects or all arrays)."""
        own = dict(self.vars)
        if not self.lists:
            return own
        out = [own]
        for lst in self.lists:
            iterations = [r.tree() for r in lst]
            if any(isinstance(t, list) for t in iterations):
                iterations = [t if isinstance(t, list) else [t] for t in iterations]
            out.append(iterations)
        return out


def _by_first(items) -> list:
    """The items' expressions, in order of first occurrence."""
    seen, out = set(), []
    for item in items:
        if id(item[1]) not in seen:
            seen.add(id(item[1]))
            out.append(item[1])
    return out


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

        exprs = [p.expression for p in parts if p.expression is not None]
        repeated = self._repeated_expressions(exprs)
        results: list[_Record] = []
        tried = 0
        for items, rest in self._parts(n, exprs, matchables):
            tried += 1
            if tried > MAX_PARTITIONS:
                break
            if not self._valid_remainder(n, rest, extras, tcs):
                continue
            results.extend(self._bind_items(items, repeated))
            results = _dedupe(results, self.limit)
            if len(results) >= self.limit:
                break
        if not results:
            # validation accepted the node, so a partition exists: either the search gave
            # up (MAX_PARTITIONS) or the partitioner disagrees with the validator.  Say
            # so, rather than binding nothing here and handing back a hollow tree.
            raise MapValidationError(
                f"no partition of the neighbourhood of {n} matches shape {getattr(S, 'id', None) or '(inline)'}"
                + (f" within {MAX_PARTITIONS} partitions" if tried > MAX_PARTITIONS else ""))
        return results

    def _repeated_expressions(self, exprs: list) -> list:
        """The repeated constraints and groups directly under ``exprs`` (not inside another
        repeated expression), in schema order: one list each in the scope's tree."""
        out: list = []

        def walk(e) -> None:
            if isinstance(e, str):
                e = self.cntxt.tripleExprFor(e)
            if e is None:
                return
            if is_repeated(e):
                out.append(e)
            elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
                for sub in e.expressions:
                    walk(sub)
        for e in exprs:
            walk(e)
        return out

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
        first.  Items are ('tc', tc, triple) or ('group', expr, items) for one iteration of a
        repeated group."""
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
            for k in range(int(min(max_, len(candidates))), min_ - 1, -1):
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
                wrapped = [('group', expr, one)] if repeated else one
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

    def _bind_items(self, items, repeated: list) -> list[_Record]:
        """Alternative records for one partition's items: each of the scope's ``repeated``
        expressions makes one list, with an iteration per item (empty when it matched
        nothing); a non-repeated constraint binds into the scope itself."""
        by_expr: dict[int, list] = {}
        alternatives: list[list[_Record]] = []
        for item in items:
            expr = item[1]
            if item[0] == 'group' or is_repeated(expr):
                by_expr.setdefault(id(expr), []).append(item)
                continue
            _, tc, t = item
            value = self._value(tc, t)
            lifted = self.lift(tc, value)
            if references_shape(tc.valueExpr):      # a nested scope: merge it into this one
                opts = []
                for sub in self.shape_expr(value, tc.valueExpr):
                    if lifted.keys() & sub.vars.keys():
                        opts.append(_Record(lifted, [[sub]], {t}))  # a name clash: keep it apart
                    else:
                        opts.append(_Record({**lifted, **sub.vars}, sub.lists, {t} | sub.triples))
                alternatives.append(opts)
            else:
                alternatives.append([_Record(lifted, triples={t})])
        for expr in repeated + [e for e in _by_first(items) if id(e) in by_expr and e not in repeated]:
            per_iteration = [self._iteration(it) for it in by_expr.pop(id(expr), [])]
            opts = []
            for combo in itertools.product(*per_iteration):
                kept = [r for r in combo if not r.empty()]
                dropped = set().union(*(r.triples for r in combo if r.empty())) if combo else set()
                opts.append(_Record(lists=[kept], triples=dropped))     # an iteration that bound nothing still matched
                if len(opts) >= self.limit:
                    break
            alternatives.append(opts or [_Record(lists=[[]])])
        return _product(alternatives, self.limit)

    def _iteration(self, item) -> list[_Record]:
        """Alternative scopes for one iteration of a repeated constraint or group."""
        if item[0] == 'group':
            expr = item[1]
            return self._bind_items(item[2], self._repeated_expressions(list(expr.expressions))) or [_Record()]
        _, tc, t = item
        value = self._value(tc, t)
        lifted = self.lift(tc, value)
        if references_shape(tc.valueExpr):
            return [_Record({NODE_KEY: value, **lifted, **sub.vars}, sub.lists, {t} | sub.triples)
                    for sub in self.shape_expr(value, tc.valueExpr)]
        return [_Record(lifted, triples={t})]

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
    kept = _dedupe(records, limit)
    return [Bindings(r.tree(), alternatives=len(kept), matched=r.all_triples()) for r in kept]


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
