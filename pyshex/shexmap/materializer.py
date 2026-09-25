"""Threaded materialization: build RDF conforming to an output schema from bindings.

A port of shex.js's ``ThreadedMaterializer`` (packages/extension-map/doc/threaded-materializer.md).

* The binding tree is flattened to a sequence of **frames** (:func:`normalize`), read
  through a cursor that stays on the current frame while it has an unused binding for a
  variable and otherwise scans forward, never back.
* Each output shape compiles to an **NFA** with four kinds of state: ``TC`` (emit one
  instance of a triple constraint), ``Split`` (OneOf / ShapeOr, in priority order),
  ``Rept`` (cardinality) and ``Match``.  A shape-valued constraint invents a blank node,
  links it and calls the nested shape's NFA; ``Match`` returns from the call.
* A **thread** is an immutable configuration -- state, call stack, cursor, emitted
  triples.  One whose variable is unbound just dies, taking its emissions and cursor
  marks with it, so a failed optional group or disjunct never disturbs its siblings.
* Threads run depth-first in greedy order (another repetition, then the emitting arm of
  an optional, then the first disjunct), except that a lookup which has to **advance to
  a later frame** is deferred until the alternatives that can still use the current
  frame have been explored.
* Every accepting thread is kept; :meth:`ThreadedMaterializer.materialize` returns the
  one that consumed the most bindings (ties: fewest bindings skipped by cursor advances,
  then most triples, then discovery order), or whichever ``prefer`` ranks first.

Beyond shex.js: ``EXTENDS`` in the output schema materializes the extended shapes' triple
constraints on the same node, and a reference to a shape that has extensions may
materialize any non-abstract one of them -- the threads decide which fits the bindings.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions
from pyshex.shexmap.bindings import (Bindings, declaration_of, expression_of, extension_candidates, map_actions,
                                     normalize, references_shape, shape_parts, shexc_prefixes, term_from_json)

UNBOUNDED = -1


class MaterializationError(ValueError):
    """No thread could build the requested shape from the bindings.

    :ivar failures: the dead ends met on the way, deepest last
    :ivar report: see :attr:`ThreadedMaterializer.last_report`
    """

    def __init__(self, message: str, failures: list | None = None, report: dict | None = None) -> None:
        failures = failures or []
        if failures:
            message += "; deepest failures: " + "; ".join(_describe(f) for f in failures[-3:])
        super().__init__(message)
        self.failures = failures
        self.report = report


def _describe(f: dict) -> str:
    what = f.get('variable') or f.get('code') or ''
    return f"{f.get('predicate', '')} {what} {f.get('error', 'unbound')}".strip()


# -- the frame cursor -------------------------------------------------------------------

@dataclass(frozen=True)
class Cursor:
    idx: int = 0                                  # current frame
    used: frozenset = frozenset()                 # (frame, variable) pairs consumed
    n: int = 0                                    # frame bindings consumed
    skipped: int = 0                              # unused bindings abandoned by advancing


def cursor_get(frames: list[dict], statics: Mapping[str, Node], cursor: Cursor, var: str):
    """(value, new cursor) for ``var``, or None when no unused binding remains."""
    if var in statics:                            # static vars: always there, never used up
        return statics[var], cursor
    for i in range(cursor.idx, len(frames)):
        if var in frames[i] and (i, var) not in cursor.used:
            used = cursor.used | {(i, var)}
            skipped = cursor.skipped + sum(1 for j in range(cursor.idx, i) for v in frames[j]
                                           if (j, v) not in used)
            return frames[i][var], Cursor(i, used, cursor.n + 1, skipped)
    return None


# -- NFAs --------------------------------------------------------------------------------

@dataclass
class State:
    type: str                                     # TC | Split | Rept | Match
    outs: list[int] = field(default_factory=list)
    tc: Any = None
    min: int = 1
    max: float = 1
    skippable: bool = False


@dataclass
class NFA:
    states: list[State]
    start: int


def _clone_into(combined: list[State], nfa: NFA) -> int:
    offset = len(combined)
    for s in nfa.states:
        combined.append(replace(s, outs=[o + offset for o in s.outs]))
    return offset


def _concat(parts: list[NFA]) -> NFA:
    """Run each part in turn against the same subject."""
    if not parts:
        return NFA([State('Match')], 0)
    states: list[State] = []
    offsets = [_clone_into(states, p) for p in parts]
    for i in range(len(parts) - 1):         # each part's Match (state 0) hands over to the next
        states[offsets[i]] = State('Split', outs=[offsets[i + 1] + parts[i + 1].start])
    return NFA(states, offsets[0] + parts[0].start)


def _split(parts: list[NFA]) -> NFA:
    """Fork over the parts, in priority order."""
    if not parts:
        return NFA([State('Match')], 0)
    states: list[State] = []
    outs = [_clone_into(states, p) + p.start for p in parts]
    states.append(State('Split', outs=outs))
    return NFA(states, len(states) - 1)


# -- threads -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CallFrame:
    nfa: NFA
    outs: tuple
    subject: Node
    repeats: tuple
    parent: CallFrame | None
    skippable: bool
    quads_mark: Any
    consumed_mark: int


@dataclass(frozen=True)
class Thread:
    nfa: NFA
    state: int
    subject: Node
    repeats: tuple                              # sorted ((state, (count, consumed_at)), ...)
    call_stack: CallFrame | None
    cursor: Cursor
    quads: Any                                  # persistent list: (triple, previous) or None
    bnode: int


def _repeats_get(repeats: tuple, state: int):
    for k, v in repeats:
        if k == state:
            return v
    return None


def _repeats_set(repeats: tuple, state: int, value) -> tuple:
    kept = tuple((k, v) for k, v in repeats if k != state)
    return tuple(sorted(kept + ((state, value),))) if value is not None else kept


def _collect(quads) -> list[tuple[Node, Node, Node]]:
    out = []
    while quads is not None:
        out.append(quads[0])
        quads = quads[1]
    out.reverse()
    seen, kept = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            kept.append(q)
    return kept


def _depth(call_stack: CallFrame | None) -> int:
    d = 0
    while call_stack is not None:
        d, call_stack = d + 1, call_stack.parent
    return d


@dataclass
class Accept:
    """An accepting thread's result."""
    triples: list[tuple[Node, Node, Node]]
    consumed: int
    skipped: int
    used: frozenset


class ThreadedMaterializer:
    """Materialize instances of an output schema from ShExMap bindings.

    :param schema: output schema, as ShExC text or a parsed ShExJ schema
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :param static_vars: variable values available everywhere, never used up
    :param prefer: comparator over :class:`Accept` s, negative when the first is better
    :param require_bindings_in_subshapes: drop optional subshapes that consume no binding
    """

    def __init__(self, schema: str | ShExJ.Schema, prefixes: Mapping[str, str] | None = None,
                 static_vars: Mapping[str, Node] | None = None,
                 prefer: Callable[[Accept, Accept], int] | None = None,
                 max_repeat: int = 50, max_call_depth: int = 50, max_steps: int = 1_000_000,
                 max_accepts: int = 20, explore_steps: int = 10_000,
                 require_bindings_in_subshapes: bool = False) -> None:
        from pyshex.utils.schema_loader import SchemaLoader
        if isinstance(schema, str):
            prefixes = {**shexc_prefixes(schema), **(prefixes or {})}
            schema = SchemaLoader().loads(schema)
            if schema is None:
                raise MaterializationError("The output schema does not parse")
        self.schema = schema
        self.cntxt = Context(None, schema)
        self.prefixes = dict(prefixes or {})
        self.statics = {k: (v if isinstance(v, Node) else term_from_json(v)) for k, v in (static_vars or {}).items()}
        self.prefer = prefer
        self.max_repeat, self.max_call_depth = max_repeat, max_call_depth
        self.max_steps, self.max_accepts, self.explore_steps = max_steps, max_accepts, explore_steps
        self.require_bindings_in_subshapes = require_bindings_in_subshapes
        self._cache: dict[int, NFA] = {}
        self._compiling: list[tuple[int, str]] = []
        self.accepts: list[Accept] = []
        self.chosen: Accept | None = None
        self.last_report: dict = {}
        self.frames: list[dict] = []

    # -- compilation --------------------------------------------------------------------
    def _compile_shape_expr(self, se, label: str | None = None) -> NFA:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                raise MaterializationError(f"Shape {se} is not defined in the output schema")
            return self._compile_decl(decl, str(se))
        return self._compile_expr(se, label or f"(inline {type(se).__name__})")

    def _compile_decl(self, decl, label: str) -> NFA:
        """A reference: the declaration itself or any non-abstract extension of it."""
        key = id(decl) * 2 + 1
        if key in self._cache:
            return self._cache[key]
        options = extension_candidates(self.cntxt, decl)
        if not options:
            raise MaterializationError(f"Shape {label} is abstract and nothing extends it")
        options.reverse()                       # the declaration itself first, then extensions
        nfa = _split([self._compile_expr(expression_of(o), str(getattr(o, 'id', label))) for o in options]) \
            if len(options) > 1 else self._compile_expr(expression_of(options[0]), label)
        self._cache[key] = nfa
        return nfa

    def _compile_expr(self, se, label: str) -> NFA:
        key = id(se) * 2
        if key in self._cache:
            return self._cache[key]
        if any(k == key for k, _ in self._compiling):
            loop = [lbl for k, lbl in self._compiling[[k for k, _ in self._compiling].index(key):]]
            raise MaterializationError("cycle in shape expressions: " + " -> ".join(loop + [label]))
        self._compiling.append((key, label))
        try:
            if isinstance(se, ShExJ.ShapeDecl):
                nfa = self._compile_expr(se.shapeExpr, label)
            elif isinstance(se, ShExJ.Shape):
                nfa = _concat([self._nfa_for_expression(p.expression) for p in shape_parts(self.cntxt, se)])
            elif isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
                parts = [self._compile_shape_expr(p) for p in se.shapeExprs
                         if not isinstance(p, ShExJ.NodeConstraint)]
                nfa = _concat(parts) if isinstance(se, ShExJ.ShapeAnd) else _split(parts)
            elif isinstance(se, ShExJ.NodeConstraint):
                nfa = NFA([State('Match')], 0)
            else:
                raise MaterializationError(f"{type(se).__name__} synthesis is not supported")
        finally:
            self._compiling.pop()
        self._cache[key] = nfa
        return nfa

    def _nfa_for_expression(self, expression) -> NFA:
        states: list[State] = [State('Match')]

        def mk(s: State) -> int:
            states.append(s)
            return len(states) - 1

        def patch(tail: list[int], target: int) -> None:
            for t in tail:
                states[t].outs.append(target)

        def walk(expr) -> tuple[int, list[int]]:
            if isinstance(expr, str):           # an inclusion: &label
                expr = self.cntxt.tripleExprFor(expr)
            if isinstance(expr, ShExJ.TripleConstraint):
                s = mk(State('TC', tc=expr))
                start, tail = s, [s]
            elif isinstance(expr, ShExJ.OneOf):
                starts, tails = [], []
                for nested in expr.expressions:
                    s, t = walk(nested)
                    starts.append(s)
                    tails.extend(t)
                start, tail = mk(State('Split', outs=starts)), tails
            elif isinstance(expr, ShExJ.EachOf):
                start = tail = None
                for nested in expr.expressions:
                    s, t = walk(nested)
                    if start is None:
                        start = s
                    else:
                        patch(tail, s)
                    tail = t
            else:
                raise MaterializationError(f"unexpected triple expression {type(expr).__name__}")
            min_ = 1 if expr.min is None else expr.min
            max_ = 1 if expr.max is None else (float('inf') if expr.max == UNBOUNDED else expr.max)
            if isinstance(expr, ShExJ.TripleConstraint):
                if min_ == 0 and max_ == 1 and self._always_synthesizable(expr):
                    return start, tail          # skipping a constant gains nothing: emit it
                if min_ == 0:
                    states[start].skippable = True
            if min_ == 1 and max_ == 1:
                return start, tail
            rept = mk(State('Rept', outs=[start], min=min_, max=max_))
            patch(tail, rept)
            return rept, [rept]

        start = 0
        if expression is not None:
            s, tail = walk(expression)
            patch(tail, 0)
            start = s
        return NFA(states, start)

    def _always_synthesizable(self, tc) -> bool:
        acts = map_actions(tc)
        if acts:
            return all(not functions.is_function_call(str(a.code or '')) and
                       self._var(str(a.code or '')) in self.statics for a in acts)
        return _single_value(tc.valueExpr) is not None

    def _var(self, code: str) -> str:
        return functions.expand_variable(code, self.prefixes)

    # -- running ------------------------------------------------------------------------
    def materialize(self, bindings, root: str | Node | None = None, start=None) -> list[tuple[Node, Node, Node]]:
        """The triples of the best materialization of ``start`` (default: the schema's start)
        rooted at ``root`` (default: a new blank node).  All distinct results are kept in
        :attr:`accepts`, the returned one in :attr:`chosen`.

        :raises MaterializationError: when no thread reaches an accepting state
        """
        tree = bindings.tree if isinstance(bindings, Bindings) else bindings
        frames = normalize(tree)
        self.frames = frames
        root = _node(root) if root is not None else BNode()
        if start is None or start is START:
            if self.schema.start is None:
                raise MaterializationError("The output schema has no start shape; name one with start=")
            nfa = self._compile_shape_expr(self.schema.start, "START")
        else:
            nfa = self._compile_shape_expr(ShExJ.IRIREF(str(start)))
        bnode_prefix = uuid.uuid4().hex[:8]

        failures: list[dict] = []
        referenced: set[str] = set()
        available = set(self.statics) | {v for f in frames for v in f}
        accepts: list[Accept] = []
        self.accepts, self.chosen = accepts, None
        by_used: dict[frozenset, Accept] = {}
        graphs_seen: set[frozenset] = set()
        total = sum(len(f) for f in frames)

        stack = [Thread(nfa, nfa.start, root, (), None, Cursor(), None, 0)]
        deferred: list[Thread] = []
        seen: set = set()
        steps = pruned = 0
        accepted_at = None
        truncated = False

        while stack or deferred:
            steps += 1
            if steps > self.max_steps:
                if accepts:
                    truncated = True
                    break
                raise MaterializationError(f"exceeded max_steps={self.max_steps}", failures,
                                           self._report(failures, referenced, available, accepts, True, pruned))
            if accepted_at is not None and steps - accepted_at > self.explore_steps:
                truncated = True
                break
            th = stack.pop() if stack else deferred.pop(0)
            key = (th.state, id(th.nfa), id(th.call_stack), th.cursor.idx, th.cursor.used, th.repeats)
            if key in seen:
                pruned += 1
                continue
            seen.add(key)
            st = th.nfa.states[th.state]

            if st.type == 'Match':
                if th.call_stack is None:
                    triples = _collect(th.quads)
                    graph_key = frozenset(triples)
                    if graph_key in graphs_seen:
                        continue
                    graphs_seen.add(graph_key)
                    existing = by_used.get(th.cursor.used)
                    if existing is not None:
                        if len(triples) > len(existing.triples):
                            existing.triples, existing.skipped = triples, th.cursor.skipped
                        continue
                    accept = Accept(triples, th.cursor.n, th.cursor.skipped, th.cursor.used)
                    by_used[th.cursor.used] = accept
                    accepts.append(accept)
                    if accepted_at is None:
                        accepted_at = steps
                    if accept.consumed >= total or len(accepts) >= self.max_accepts:
                        break
                    continue
                frame = th.call_stack
                # vacuous descent: an optional subshape that emitted and consumed nothing
                # would leave a dangling link; the skip arm already covers it
                if frame.skippable and th.cursor.n == frame.consumed_mark and \
                        (th.quads is frame.quads_mark or self.require_bindings_in_subshapes):
                    continue
                for out in frame.outs:
                    stack.append(replace(th, nfa=frame.nfa, state=out, subject=frame.subject,
                                         repeats=frame.repeats, call_stack=frame.parent))

            elif st.type == 'Split':
                for out in reversed(st.outs):   # first disjunct explored first
                    stack.append(replace(th, state=out))

            elif st.type == 'Rept':
                count, at = _repeats_get(th.repeats, th.state) or (0, -1)
                if count >= st.min:             # exit (lower priority); reset for re-entry
                    stack.append(replace(th, state=st.outs[1], repeats=_repeats_set(th.repeats, th.state, None)))
                # another iteration -- only if the last one consumed a frame binding, or
                # constant-only subexpressions would repeat to max_repeat
                if count < min(st.max, self.max_repeat) and (count == 0 or th.cursor.n > at):
                    stack.append(replace(th, state=st.outs[0],
                                         repeats=_repeats_set(th.repeats, th.state, (count + 1, th.cursor.n))))

            elif st.type == 'TC':
                succs: list[Thread] = []
                self._step(th, st, frames, succs, failures, referenced, bnode_prefix)
                if succs and succs[0].cursor.idx > th.cursor.idx:
                    deferred.extend(succs)      # advancing frames is a choice: explore in-frame first
                else:
                    stack.extend(succs)
            else:
                raise MaterializationError(f"unexpected NFA state {st.type}")

        report = self._report(failures, referenced, available, accepts, truncated, pruned)
        if not accepts:
            raise MaterializationError("no thread reached an accepting state", failures, report)
        best = accepts[0]
        for a in accepts[1:]:
            if self._better(a, best):
                best = a
        self.chosen = best
        return best.triples

    def _better(self, a: Accept, b: Accept) -> bool:
        if self.prefer is not None:
            return self.prefer(a, b) < 0
        return (a.consumed, -a.skipped, len(a.triples)) > (b.consumed, -b.skipped, len(b.triples))

    def _report(self, failures, referenced, available, accepts, truncated, pruned) -> dict:
        seen, unbound = set(), []
        for f in failures:
            v = f.get('variable')
            k = (v, f.get('predicate'))
            if v and v not in available and k not in seen:
                seen.add(k)
                unbound.append(f)
        self.last_report = {
            'unbound_variables': unbound,
            'unused_statics': [s for s in self.statics if s not in referenced],
            'alternatives': len(accepts),
            'exploration_truncated': truncated,
            'configs_pruned': pruned,
        }
        return self.last_report

    def _step(self, th: Thread, st: State, frames, succs, failures, referenced, bnode_prefix) -> None:
        """Emit one instance of a triple constraint; successors go to ``succs``."""
        tc = st.tc
        pred = URIRef(str(tc.predicate))

        def triple(obj: Node):
            if tc.inverse:
                if isinstance(obj, Literal):
                    return None                 # a literal cannot be a subject
                return (obj, pred, th.subject)
            return (th.subject, pred, obj)

        acts = map_actions(tc)
        if acts:
            cursor = th.cursor
            quads = th.quads
            for act in acts:
                code = str(act.code or '')
                if functions.is_function_call(code):
                    def get(v: str):
                        nonlocal cursor
                        referenced.add(v)
                        hit = cursor_get(frames, self.statics, cursor, v)
                        if hit is None:
                            return None
                        value, cursor = hit
                        return value
                    try:
                        value = functions.lower(code, get, self.prefixes)
                    except functions.MapFunctionError as e:
                        failures.append({'predicate': str(pred), 'tc': tc, 'code': code, 'error': str(e)})
                        return
                    if value is None:
                        failures.append({'predicate': str(pred), 'tc': tc, 'code': code, 'error': 'unbound'})
                        return
                else:
                    try:
                        var = self._var(code)
                    except functions.MapFunctionError as e:
                        failures.append({'predicate': str(pred), 'tc': tc, 'code': code, 'error': str(e)})
                        return
                    referenced.add(var)
                    hit = cursor_get(frames, self.statics, cursor, var)
                    if hit is None:
                        failures.append({'predicate': str(pred), 'tc': tc, 'variable': var, 'frame': cursor.idx})
                        return
                    value, cursor = hit
                t = triple(value)
                if t is None:
                    failures.append({'predicate': str(pred), 'tc': tc, 'error': 'literal subject of inverse'})
                    return
                quads = (t, quads)
            for out in st.outs:
                succs.append(replace(th, state=out, cursor=cursor, quads=quads))
            return

        constant = _single_value(tc.valueExpr)
        if constant is not None:
            t = triple(constant)
            if t is None:
                failures.append({'predicate': str(pred), 'tc': tc, 'error': 'literal subject of inverse'})
                return
            for out in st.outs:
                succs.append(replace(th, state=out, quads=(t, th.quads)))
            return

        if references_shape(tc.valueExpr):
            if _depth(th.call_stack) >= self.max_call_depth:
                failures.append({'predicate': str(pred), 'tc': tc, 'error': 'exceeded max_call_depth'})
                return
            sub = self._compile_shape_expr(tc.valueExpr)
            bnode = BNode(f"{bnode_prefix}t{th.bnode}")
            quads = (triple(bnode), th.quads)
            succs.append(Thread(sub, sub.start, bnode, (),
                                CallFrame(th.nfa, tuple(st.outs), th.subject, th.repeats, th.call_stack,
                                          st.skippable, quads, th.cursor.n),
                                th.cursor, quads, th.bnode + 1))
            return

        failures.append({'predicate': str(pred), 'tc': tc,
                         'error': f"cannot synthesize {type(tc.valueExpr).__name__ if tc.valueExpr else 'any value'}"
                                  " without a Map action"})


def _single_value(value_expr) -> Node | None:
    if not isinstance(value_expr, ShExJ.NodeConstraint) or not value_expr.values or len(value_expr.values) != 1:
        return None
    v = value_expr.values[0]
    if isinstance(v, ShExJ.ObjectLiteral):
        return Literal(v.value, lang=v.language, datatype=URIRef(v.type) if v.type else None)
    if isinstance(v, str):
        return URIRef(str(v))
    return None     # stems, ranges and languages do not name one value


def _node(term) -> Node:
    if isinstance(term, (URIRef, BNode)):
        return term
    return BNode(str(term)[2:]) if str(term).startswith('_:') else URIRef(str(term))


def materialize(schema: str | ShExJ.Schema, bindings, root: str | Node | None = None, start=None,
                static_vars: Mapping[str, Node] | None = None, prefixes: Mapping[str, str] | None = None,
                graph: Graph | None = None, **options) -> Graph:
    """Materialize ``root`` as an instance of the output schema from ``bindings``.

    A convenience over :class:`ThreadedMaterializer` (which also exposes the alternative
    materializations); ``options`` are passed to its constructor.

    :param schema: output schema, as ShExC text or a parsed ShExJ schema
    :param bindings: :class:`Bindings`, or a binding tree
    :param root: the node to build; a ``_:`` string makes a blank node; default a new one
    :param start: shape label to build; defaults to the schema's start
    :param static_vars: extra variable values, shared everywhere (shex.js ``staticVars``)
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :param graph: graph to add to; a new one by default
    :raises MaterializationError: when the shape cannot be built
    """
    m = ThreadedMaterializer(schema, prefixes=prefixes, static_vars=static_vars, **options)
    triples = m.materialize(bindings, root, start=start)
    graph = graph if graph is not None else Graph()
    for prefix, ns in m.prefixes.items():
        graph.bind(prefix, ns, override=False)
    for t in triples:
        graph.add(t)
    return graph
