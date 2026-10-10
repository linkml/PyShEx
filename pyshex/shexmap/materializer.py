"""Materialization by iteration scopes: build RDF conforming to an output schema from bindings.

The binding tree is read as a **scope tree** (:mod:`pyshex.shexmap.scopes`): a scope's own
bindings, and one list of iteration scopes per repeated constraint or group of the input.
Nothing is flattened and nothing is consumed:

* A constraint with a Map variable **reads** it from the scope it is evaluated at, or from
  the nearest ancestor scope that binds it.  Reading marks nothing, so a parent's binding
  can be read in every item, and twice in one.  A variable bound nowhere on that chain
  fails the constraint.
* A **repetition** in the output schema iterates one list of the input: the deepest list
  its body's variables are bound at (nested repetitions count through their parent list).
  Its body runs once per iteration of that list, in list order, at that iteration's
  scope; an iteration whose body fails is skipped; the count of successful iterations
  must reach the minimum, and the repetition stops at the maximum.  A body whose
  variables are all bound at or above the current scope runs once, there.  A body whose
  variables live in two lists neither of which contains the other is ill-formed, and
  says so.
* **Choices** (``OneOf``, ``ShapeOr``, an optional constraint, a shape with extensions)
  yield alternatives, per scope; the alternatives of the parts of a group or conjunction
  combine by product, pruned to the best ``max_accepts`` as they combine.
* Every complete alternative is an :class:`Accept`; :meth:`ThreadedMaterializer.materialize`
  returns the one that read the most distinct bindings (ties: most triples, then schema
  order), or whichever ``prefer`` ranks first, and keeps the rest in
  :attr:`~ThreadedMaterializer.accepts`.
* A value a Map code produces must **satisfy the constraint's value expression** when
  that is a node constraint (datatype, value set, facets, node kind).  A plain literal
  whose lexical form is valid for the constraint's datatype is retyped to it, so what
  ``regex()`` and ``hashmap()`` produce can land in a typed constraint; any other mismatch
  fails the constraint like an unbound variable, so an optional or another disjunct can
  take over (``check_values=False`` turns this off).
* A shape-valued constraint that also carries a Map variable **names** its node: the
  bound value is the node and the nested shape is materialized on it.  One that carries
  ``%Map:{ id(v:a, v:b) %}`` is **keyed**: its node is a function of the shape and the
  values read for the key, so two constraints, or two iterations, with the same key make
  the same node and their arcs merge -- grouping by value, and a shared reference.  A
  key of one IRI or blank node is that node itself; ``id(@node)`` reuses the input node
  the enclosing iteration matched, so a schema maps a graph onto itself node for node.
  Otherwise the node is a blank node determined by the root, the constraint, and the
  scope (its ``@node`` when it is an iteration, else its path), so two runs over the same
  bindings agree, and materializing the same root twice adds nothing.

This replaces the frame-cursor search ported from shex.js's ``ThreadedMaterializer`` (kept
as the class name); ``docs/shexmap-semantics-draft.md`` is the normative description and
``docs/shexmap-structural-plan.md`` the reasons.  ``EXTENDS`` in the output schema
materializes the extended shapes' constraints on the same node, and a reference to a
shape that has extensions may materialize any non-abstract one of them.
"""
from __future__ import annotations

import hashlib
import itertools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ShExJSG import ShExJ
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_4_node_constraints import satisfiesNodeConstraint
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions
from pyshex.shexmap.bindings import (Bindings, declaration_of, expression_of, extension_candidates, map_actions,
                                     references_shape, shape_parts, shexc_prefixes, term_from_json)
from pyshex.shexmap.scopes import BindingTreeError, ListPath, Scope, ScopeTree

UNBOUNDED = -1


class MaterializationError(ValueError):
    """No alternative materializes the requested shape from the bindings.

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


# -- results ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Result:
    """One way to materialize something: its triples, where each came from, and the bindings
    it read."""
    quads: tuple = ()
    reads: frozenset = frozenset()          # (scope path, variable)
    sources: tuple = ()                     # parallel to quads: see Accept.provenance

    def then(self, other: Result) -> Result:
        return Result(self.quads + other.quads, self.reads | other.reads, self.sources + other.sources)


EMPTY = Result()


def _source(tc, scope: Scope, reads=(), statics=(), **kind) -> dict:
    """The provenance of one triple: the constraint, the input scope it was evaluated at (its
    path and the node it matched), the bindings and static variables read for it, and how
    the object arose."""
    return {'tc': tc, 'predicate': str(tc.predicate), 'scope': scope.path, 'node': scope.nearest_node(),
            'reads': tuple(reads), 'statics': tuple(statics), **kind}


def _rank(r: Result) -> tuple[int, int]:
    return (len(r.reads), len(r.quads))


@dataclass
class Accept:
    """A complete materialization.

    :ivar provenance: one record per triple: ``tc`` and ``predicate`` (the output constraint),
        ``scope`` and ``node`` (the input iteration's path, and the node it matched), ``reads``
        (the ``(scope path, variable)`` bindings read for the object), ``statics`` (the static
        variables read for it), and one of
        ``variable``/``code`` (a Map code's value), ``constant`` (a value the schema names),
        ``structural`` (a link to a minted node), ``named`` (a node a variable names) or
        ``keyed`` (an ``id()`` node) -- the correspondence between output and input
    """
    triples: list[tuple[Node, Node, Node]]
    consumed: int                           # distinct bindings read
    skipped: int                            # always 0: nothing is passed over any more
    used: frozenset                         # the (scope path, variable) addresses read
    provenance: list[dict] = None


class ThreadedMaterializer:
    """Materialize instances of an output schema from ShExMap bindings.

    :param schema: output schema, as ShExC text or a parsed ShExJ schema
    :param prefixes: prefixes for ShExMap variable names; read from ShExC text when omitted
    :param static_vars: variable values available everywhere
    :param prefer: comparator over :class:`Accept` s, negative when the first is better
    :param max_repeat: cap on the iterations of one repetition; ``None`` for none
    :param max_call_depth: cap on nested shape calls (recursive schemas)
    :param max_accepts: how many alternatives to keep, at every level and at the end
    :param require_bindings_in_subshapes: drop optional subshapes that read no binding
    :param check_values: check bound values against node constraints, retyping plain
        literals whose lexical form fits the datatype
    :param max_steps, explore_steps: accepted for compatibility; the search has no budget
        to spend any more
    """

    def __init__(self, schema: str | ShExJ.Schema, prefixes: Mapping[str, str] | None = None,
                 static_vars: Mapping[str, Node] | None = None,
                 prefer: Callable[[Accept, Accept], int] | None = None,
                 max_repeat: int | None = None, max_call_depth: int = 50, max_steps: int = 1_000_000,
                 max_accepts: int = 20, explore_steps: int = 10_000,
                 require_bindings_in_subshapes: bool = False, check_values: bool = True) -> None:
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
        self.max_accepts = max_accepts
        self.require_bindings_in_subshapes = require_bindings_in_subshapes
        self.check_values = check_values
        self.accepts: list[Accept] = []
        self.chosen: Accept | None = None
        self.provenance: list[dict] | None = None
        self.last_report: dict = {}
        self.tree: ScopeTree | None = None
        self._lists: dict[int, tuple] = {}          # id(repeated expr) -> (list path or None,)
        self._tc_index: dict[int, int] = {}
        self._active: list[tuple[tuple, str]] = []
        self._failures: list[dict] = []
        self._referenced: set[str] = set()
        self._dropped = 0

    # -- running ------------------------------------------------------------------------
    def materialize(self, bindings, root: str | Node | None = None, start=None) -> list[tuple[Node, Node, Node]]:
        """The triples of the best materialization of ``start`` (default: the schema's start)
        rooted at ``root`` (default: a new blank node).  The alternatives are kept in
        :attr:`accepts`, best first; the returned one is :attr:`chosen`.

        :raises MaterializationError: when nothing materializes, or the bindings are not a
            scope tree, or a repetition reads variables from unrelated lists
        """
        tree = bindings.tree if isinstance(bindings, Bindings) else bindings
        try:
            self.tree = ScopeTree(tree)
        except BindingTreeError as e:
            raise MaterializationError(str(e)) from e
        root = _node(root) if root is not None else BNode()
        if start is None or start is START:
            if self.schema.start is None:
                raise MaterializationError("The output schema has no start shape; name one with start=")
            se = self.schema.start
        else:
            se = ShExJ.IRIREF(str(start))
        self._root = root
        self._lists, self._tc_index, self._active = {}, {}, []
        self._failures, self._referenced, self._dropped = [], set(), 0

        results = self._shape_expr(se, self.tree.root, root, 0, "START" if start is None else str(start))
        seen: set[frozenset] = set()
        accepts: list[Accept] = []
        for r in sorted(results, key=_rank, reverse=True):       # stable: schema order among ties
            triples, provenance = _distinct(r.quads, r.sources)
            key = frozenset(triples)
            if key in seen:
                continue
            seen.add(key)
            accepts.append(Accept(triples, len(r.reads), 0, r.reads, provenance))
        self.accepts = accepts
        report = self._report(len(accepts))
        if not accepts:
            raise MaterializationError("nothing materializes the shape from these bindings", self._failures, report)
        best = accepts[0]
        if self.prefer is not None:
            for a in accepts[1:]:
                if self.prefer(a, best) < 0:
                    best = a
        self.chosen = best
        self.provenance = best.provenance
        return best.triples

    def update(self, graph: Graph, bindings, root: str | Node | None, start=None) -> tuple[set, set]:
        """Materialize into ``graph``, replacing what the output schema currently holds at
        ``root``: the schema, used as an input schema on ``graph`` at ``root``, says which
        triples it governs there; those no longer produced are removed, the new ones added,
        and everything else is left alone.  Returns ``(added, removed)``.

        Whether the graph holds an earlier materialization is decided by the predicates the
        output schema's start shape constrains: a triple at ``root`` on one of them means
        there is something to replace, and it must then conform.

        :raises MaterializationError: when ``graph`` holds something at ``root`` that does not
            conform to the output schema (so what to replace cannot be told), or nothing
            materializes
        """
        from pyshex.shexmap.bindings import MapValidationError, bind_all
        root = _node(root) if root is not None else BNode()
        new = set(self.materialize(bindings, root, start=start))
        current: set = set()
        if self._holds_something(graph, root, start):
            try:
                for b in bind_all(graph, self.schema, root, start=start, prefixes=self.prefixes):
                    current |= set(b.matched)
            except MapValidationError as e:
                raise MaterializationError(f"{root.n3()} holds something that does not conform to the output "
                                           f"schema, so what to replace cannot be told: {e}") from e
        removed = current - new
        added = {t for t in new if t not in graph}
        for t in removed:
            graph.remove(t)
        for t in new:
            graph.add(t)
        return added, removed

    def _holds_something(self, graph: Graph, root: Node, start) -> bool:
        """Whether ``graph`` has, at ``root``, a triple on a predicate the output schema's start
        shape constrains: the mark of an earlier materialization (or of a conflict)."""
        se = self.schema.start if start is None or start is START else ShExJ.IRIREF(str(start))
        for pred, inverse in self._own_predicates(se, set()):
            if any(graph.triples((None, pred, root) if inverse else (root, pred, None))):
                return True
        return False

    def _own_predicates(self, se, seen: set) -> set:
        """(predicate, inverse) of the constraints on the shape's own node, extensions included."""
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            return set().union(*(self._own_predicates(expression_of(o), seen)
                                 for o in (extension_candidates(self.cntxt, decl) if decl is not None else [])))
        if se is None or id(se) in seen:
            return set()
        seen.add(id(se))
        if isinstance(se, ShExJ.ShapeDecl):
            return self._own_predicates(se.shapeExpr, seen)
        if isinstance(se, ShExJ.Shape):
            out: set = set()
            stack = [p.expression for p in shape_parts(self.cntxt, se) if p.expression is not None]
            while stack:
                e = stack.pop()
                if isinstance(e, str):
                    e = self.cntxt.tripleExprFor(e)
                if isinstance(e, ShExJ.TripleConstraint):
                    out.add((URIRef(str(e.predicate)), bool(e.inverse)))
                elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
                    stack.extend(e.expressions)
            return out
        if isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            return set().union(*(self._own_predicates(p, seen) for p in se.shapeExprs))
        return set()

    def _report(self, found: int) -> dict:
        available = set(self.statics) | (self.tree.variables() if self.tree else set())
        seen, unbound = set(), []
        for f in self._failures:
            v = f.get('variable')
            k = (v, f.get('predicate'))
            if v and v not in available and k not in seen:
                seen.add(k)
                unbound.append(f)
        self.last_report = {
            'unbound_variables': unbound,
            'unused_statics': [s for s in self.statics if s not in self._referenced],
            'alternatives': found,
            'exploration_truncated': self._dropped > 0,
            'configs_pruned': self._dropped,
        }
        return self.last_report

    # -- shape expressions --------------------------------------------------------------
    def _shape_expr(self, se, scope: Scope, subject: Node, depth: int, label: str | None = None) -> list[Result]:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                raise MaterializationError(f"Shape {se} is not defined in the output schema")
            options = extension_candidates(self.cntxt, decl)
            if not options:
                raise MaterializationError(f"Shape {se} is abstract and nothing extends it")
            options.reverse()                   # the declaration itself first, then its extensions
            return self._guarded(('ref', id(decl), scope.path, subject), str(se), lambda: self._prune(
                [r for o in options for r in self._shape_expr(expression_of(o), scope, subject, depth, str(se))]))
        label = label or f"(inline {type(se).__name__})"
        if isinstance(se, ShExJ.ShapeDecl):
            return self._shape_expr(se.shapeExpr, scope, subject, depth, label)
        if isinstance(se, ShExJ.Shape):
            parts = [p.expression for p in shape_parts(self.cntxt, se)]
            return self._guarded(('shape', id(se), scope.path, subject), label, lambda: self._all(
                [self._expression(e, scope, subject, depth) if e is not None else [EMPTY] for e in parts]))
        if isinstance(se, ShExJ.ShapeAnd):
            return self._guarded(('and', id(se), scope.path, subject), label, lambda: self._all(
                [self._shape_expr(p, scope, subject, depth) for p in se.shapeExprs
                 if not isinstance(p, ShExJ.NodeConstraint)]))
        if isinstance(se, ShExJ.ShapeOr):
            return self._guarded(('or', id(se), scope.path, subject), label, lambda: self._prune(
                [r for p in se.shapeExprs if not isinstance(p, ShExJ.NodeConstraint)
                 for r in self._shape_expr(p, scope, subject, depth)]))
        if isinstance(se, ShExJ.NodeConstraint):
            return [EMPTY]
        raise MaterializationError(f"{type(se).__name__} synthesis is not supported")

    def _guarded(self, key: tuple, label: str, run: Callable[[], list[Result]]) -> list[Result]:
        """Evaluate, refusing a shape expression that reaches itself at the same scope and
        subject through references alone (``<A> @<B> OR ...``, ``<B> @<A> OR ...``)."""
        for i, (k, _) in enumerate(self._active):
            if k == key:
                raise MaterializationError("cycle in shape expressions: " +
                                           " -> ".join(lbl for _, lbl in self._active[i:]) + " -> " + label)
        self._active.append((key, label))
        try:
            return run()
        finally:
            self._active.pop()

    # -- triple expressions -------------------------------------------------------------
    def _expression(self, expr, scope: Scope, subject: Node, depth: int) -> list[Result]:
        if isinstance(expr, str):               # an inclusion: &label
            expr = self.cntxt.tripleExprFor(expr)
        min_ = 1 if expr.min is None else expr.min
        max_ = 1 if expr.max is None else (math.inf if expr.max == UNBOUNDED else expr.max)
        if min_ == 1 and max_ == 1:
            return self._once(expr, scope, subject, depth, False)
        return self._repetition(expr, min_, max_, scope, subject, depth)

    def _once(self, expr, scope: Scope, subject: Node, depth: int, skippable: bool) -> list[Result]:
        """The alternatives for one occurrence of ``expr``, cardinality aside."""
        if isinstance(expr, ShExJ.TripleConstraint):
            return self._tc(expr, scope, subject, depth, skippable)
        if isinstance(expr, ShExJ.EachOf):
            return self._all([self._expression(e, scope, subject, depth) for e in expr.expressions])
        if isinstance(expr, ShExJ.OneOf):
            return self._prune([r for e in expr.expressions for r in self._expression(e, scope, subject, depth)])
        raise MaterializationError(f"unexpected triple expression {type(expr).__name__}")

    def _repetition(self, expr, min_: int, max_: float, scope: Scope, subject: Node, depth: int) -> list[Result]:
        list_path = self._list_path(expr)
        skippable = min_ == 0
        if list_path is None or len(list_path) <= scope.depth:
            # the body reads nothing below this scope: it runs once, here
            if min_ > 1:
                return []
            body = self._once(expr, scope, subject, depth, skippable)
            return body if body else ([EMPTY] if min_ == 0 else [])
        cap = max_ if self.max_repeat is None else min(max_, self.max_repeat)
        results, count = [EMPTY], 0
        for item in scope.descendants_at(list_path):
            if count >= cap:
                break
            body = self._once(expr, item, subject, depth, skippable)
            if not body:
                continue                        # this item does not fit the body: skip it
            results = self._all([results, body])
            count += 1
        return results if count >= min_ else []

    def _tc(self, tc: ShExJ.TripleConstraint, scope: Scope, subject: Node, depth: int, skippable: bool) -> list[Result]:
        pred = URIRef(str(tc.predicate))

        def triple(obj: Node):
            if tc.inverse:
                if isinstance(obj, Literal):
                    self._failures.append({'predicate': str(pred), 'tc': tc, 'error': 'literal subject of inverse'})
                    return None
                return (obj, pred, subject)
            return (subject, pred, obj)

        acts = map_actions(tc)
        if any(functions.is_key_code(str(a.code or '')) for a in acts):
            return self._keyed(tc, acts, scope, subject, depth, skippable, triple)
        if acts:
            reads: set = set()
            statics_read: list = []

            def get(v: str):
                self._referenced.add(v)
                if v in self.statics:
                    statics_read.append(v)
                    return self.statics[v]
                hit = scope.lookup(v)
                if hit is None:
                    return None
                value, at = hit
                reads.add((at.path, v))
                return value

            quads = []
            objects = []
            sources = []
            for act in acts:
                code = str(act.code or '')
                before = set(reads)
                del statics_read[:]
                try:
                    if functions.is_function_call(code):
                        value = functions.lower(code, get, self.prefixes)
                        if value is None:
                            self._failures.append({'predicate': str(pred), 'tc': tc, 'code': code, 'error': 'unbound'})
                            return []
                        how = {'code': code.strip()}
                    else:
                        var = functions.expand_variable(code, self.prefixes)
                        value = get(var)
                        if value is None:
                            self._failures.append({'predicate': str(pred), 'tc': tc, 'variable': var, 'scope': scope.path})
                            return []
                        how = {'variable': var}
                except functions.MapFunctionError as e:
                    self._failures.append({'predicate': str(pred), 'tc': tc, 'code': code, 'error': str(e)})
                    return []
                if self.check_values:
                    value = self._checked(tc, value)
                    if value is None:
                        self._failures.append({'predicate': str(pred), 'tc': tc, 'code': code,
                                               'error': 'the value does not satisfy the value expression'})
                        return []
                t = triple(value)
                if t is None:
                    return []
                quads.append(t)
                objects.append(value)
                sources.append(_source(tc, scope, sorted(reads - before), list(statics_read), **how))
            if references_shape(tc.valueExpr) and len(objects) == 1 and not isinstance(objects[0], Literal):
                # the variable names the node: materialize the nested shape on it
                if depth >= self.max_call_depth:
                    self._failures.append({'predicate': str(pred), 'tc': tc, 'error': 'exceeded max_call_depth'})
                    return []
                sources[0]['named'] = True
                result = Result(tuple(quads), frozenset(reads), tuple(sources))
                return [result.then(n) for n in self._shape_expr(tc.valueExpr, scope, objects[0], depth + 1)]
            return [Result(tuple(quads), frozenset(reads), tuple(sources))]

        constant = _single_value(tc.valueExpr)
        if constant is not None:
            t = triple(constant)
            return [Result((t,), frozenset(), (_source(tc, scope, constant=True),))] if t is not None else []

        if references_shape(tc.valueExpr):
            if depth >= self.max_call_depth:
                self._failures.append({'predicate': str(pred), 'tc': tc, 'error': 'exceeded max_call_depth'})
                return []
            node = self._mint(tc, scope, depth)
            link = triple(node)
            if link is None:
                return []
            out = []
            for n in self._shape_expr(tc.valueExpr, scope, node, depth + 1):
                if skippable and not n.reads and (not n.quads or self.require_bindings_in_subshapes):
                    continue                    # an optional island nothing asked for
                out.append(Result((link,) + n.quads, n.reads, (_source(tc, scope, structural=True),) + n.sources))
            return out

        self._failures.append({'predicate': str(pred), 'tc': tc,
                               'error': f"cannot synthesize {type(tc.valueExpr).__name__ if tc.valueExpr else 'any value'}"
                                        " without a Map action"})
        return []

    def _keyed(self, tc, acts, scope: Scope, subject: Node, depth: int, skippable: bool, triple) -> list[Result]:
        """A shape-valued constraint with ``id(...)``: the node is a function of the key."""
        pred = str(tc.predicate)
        if len(acts) > 1:
            raise MaterializationError(f"id() must be the only Map code on the constraint at {pred}")
        if not references_shape(tc.valueExpr):
            raise MaterializationError(f"id() at {pred} needs a shape-valued constraint: it names a node, not a value")
        code = str(acts[0].code or '')
        try:
            terms = functions.key_terms(code, self.prefixes)
        except functions.MapFunctionError as e:
            raise MaterializationError(str(e)) from e
        reads: set = set()
        statics_read: list = []
        missing: list = []

        def get(a: str):
            self._referenced.add(a)
            if a in self.statics:
                statics_read.append(a)
                return self.statics[a]
            hit = scope.lookup(a)
            if hit is None:
                missing.append(a)
                return None
            value, at = hit
            reads.add((at.path, a))
            return value

        values = []
        for term in terms:
            if term == functions.NODE_ARGUMENT:
                value = scope.nearest_node()
                if value is None:
                    self._failures.append({'predicate': pred, 'tc': tc, 'code': code, 'error': 'no @node in scope'})
                    return []
            elif isinstance(term, functions.Template):
                value = term.expand(get)
            else:
                value = get(term)
            if value is None:
                self._failures.append({'predicate': pred, 'tc': tc, 'variable': missing[-1] if missing else code,
                                       'scope': scope.path})
                return []
            values.append(value)
        if len(values) == 1 and not isinstance(values[0], Literal):
            node = values[0]
        else:
            shape = str(tc.valueExpr) if isinstance(tc.valueExpr, str) else f"inline{self._tc_index.setdefault(id(tc), len(self._tc_index))}"
            node = BNode("k" + _digest(shape, *(v.n3() for v in values)))
        if depth >= self.max_call_depth:
            self._failures.append({'predicate': pred, 'tc': tc, 'error': 'exceeded max_call_depth'})
            return []
        link = triple(node)
        if link is None:
            return []
        out = []
        for n in self._shape_expr(tc.valueExpr, scope, node, depth + 1):
            if skippable and not (n.reads | reads) and (not n.quads or self.require_bindings_in_subshapes):
                continue
            out.append(Result((link,) + n.quads, frozenset(reads) | n.reads,
                              (_source(tc, scope, sorted(reads), statics_read, keyed=code.strip()),) + n.sources))
        return out

    # -- value expressions --------------------------------------------------------------
    def _checked(self, tc, value: Node) -> Node | None:
        """``value`` if it satisfies the constraint's value expression, a retyped copy of a
        plain literal whose lexical form fits the expression's datatype, or None."""
        se = self._resolve(tc.valueExpr)
        if se is None or not _is_node_constraint(se):
            return value                    # nothing to check: a shape, or no expression at all
        if self._satisfies(se, value):
            return value
        dt = self._datatype_of(se)
        if dt and isinstance(value, Literal) and value.datatype is None and value.language is None \
                and _valid_lexical(str(value), str(dt)) is not False:
            retyped = Literal(str(value), datatype=URIRef(str(dt)))
            if self._satisfies(se, retyped):
                return retyped
        return None

    def _datatype_of(self, se):
        """The datatype a value expression asks for: its own, or the one conjunct that has one."""
        se = self._resolve(se)
        if isinstance(se, ShExJ.NodeConstraint):
            return se.datatype
        if isinstance(se, ShExJ.ShapeAnd):
            found = [dt for dt in (self._datatype_of(p) for p in se.shapeExprs) if dt]
            return found[0] if len(set(map(str, found))) == 1 else None
        return None

    def _resolve(self, se):
        for _ in range(100):
            if isinstance(se, str):
                decl = declaration_of(self.cntxt, se)
                if decl is None:
                    return None
                se = expression_of(decl)
            elif isinstance(se, ShExJ.ShapeDecl):
                se = se.shapeExpr
            else:
                return se
        return None

    def _satisfies(self, se, value: Node) -> bool:
        se = self._resolve(se)
        if isinstance(se, ShExJ.NodeConstraint):
            saved = self.cntxt.current_node
            self.cntxt.current_node = ParseNode(satisfiesNodeConstraint, se, value, self.cntxt)
            try:
                return bool(satisfiesNodeConstraint(self.cntxt, value, se))
            finally:
                self.cntxt.current_node = saved
        if isinstance(se, ShExJ.ShapeAnd):
            return all(self._satisfies(p, value) for p in se.shapeExprs if _is_node_constraint(self._resolve(p)))
        if isinstance(se, ShExJ.ShapeOr):
            return any(self._satisfies(p, value) for p in se.shapeExprs)
        if isinstance(se, ShExJ.ShapeNot):
            return not self._satisfies(se.shapeExpr, value)
        return True                         # a shape: the nested materialization is the check

    def _mint(self, tc, scope: Scope, depth: int) -> BNode:
        """The node for a shape-valued constraint without a key: determined by the root, the
        constraint, its call depth, and the scope -- the input node the scope matched when it
        is an iteration, else its path -- so a materialization is reproducible and two runs
        over the same input agree."""
        n = self._tc_index.setdefault(id(tc), len(self._tc_index))
        where = scope.node.n3() if scope.node is not None else "p" + "_".join(map(str, scope.path))
        return BNode(f"m{_digest(self._root.n3(), str(n), str(depth), where)}")

    # -- combining alternatives ---------------------------------------------------------
    def _all(self, parts: list[list[Result]]) -> list[Result]:
        """Every combination of one alternative per part, pruned as it grows."""
        acc = [EMPTY]
        for alternatives in parts:
            if not alternatives:
                return []
            acc = self._prune([a.then(b) for a in acc for b in alternatives])
        return acc

    def _prune(self, results: list[Result]) -> list[Result]:
        if len(results) <= self.max_accepts:
            return results
        ranked = sorted(range(len(results)), key=lambda i: _rank(results[i]), reverse=True)[:self.max_accepts]
        self._dropped += len(results) - len(ranked)
        return [results[i] for i in sorted(ranked)]

    # -- which list a repetition iterates -----------------------------------------------
    def _list_path(self, expr) -> ListPath | None:
        key = id(expr)
        if key not in self._lists:
            self._lists[key] = (self._analyse(expr),)
        return self._lists[key][0]

    def _analyse(self, expr) -> ListPath | None:
        """The list the repetition ``expr`` iterates: the deepest list its body's variables are
        bound at, nested repetitions counting through their parent list."""
        direct: set[str] = set()
        nested: list = []
        self._collect(expr, direct, nested, set(), top=True)
        bound = self.tree.bound_at
        candidates: dict[ListPath, str] = {}
        for v in direct:
            if v in bound:
                candidates.setdefault(bound[v], v)
        for r in nested:
            lp = self._list_path(r)
            if lp:
                candidates.setdefault(lp[:-1], f"the repetition at {_predicates(r)}")
        if not candidates:
            return None
        deepest = max(candidates, key=len)
        for lp, why in candidates.items():
            if deepest[:len(lp)] != lp:
                raise MaterializationError(
                    f"the repetition at {_predicates(expr)} reads from unrelated lists: "
                    f"{why} is bound at {lp} and {candidates[deepest]} at {deepest}")
        return deepest

    def _collect(self, expr, direct: set[str], nested: list, seen: set, top: bool) -> None:
        """Variables read directly in ``expr``'s body and the repetitions directly inside it."""
        if isinstance(expr, str):
            expr = self.cntxt.tripleExprFor(expr)
        if expr is None or id(expr) in seen:
            return
        seen.add(id(expr))
        if not top and not (expr.min in (None, 1) and expr.max in (None, 1)):
            nested.append(expr)
            return
        if isinstance(expr, ShExJ.TripleConstraint):
            for act in map_actions(expr):
                code = str(act.code or '')
                try:
                    if functions.is_function_call(code):
                        direct.update(functions.variables_of(code, self.prefixes))
                    else:
                        direct.add(functions.expand_variable(code, self.prefixes))
                except functions.MapFunctionError:
                    pass
            if references_shape(expr.valueExpr):
                self._collect_shape(expr.valueExpr, direct, nested, seen)
        elif isinstance(expr, (ShExJ.EachOf, ShExJ.OneOf)):
            for e in expr.expressions:
                self._collect(e, direct, nested, seen, top=False)

    def _collect_shape(self, se, direct: set[str], nested: list, seen: set) -> None:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                return
            for o in extension_candidates(self.cntxt, decl):
                self._collect_shape(expression_of(o), direct, nested, seen)
            return
        if id(se) in seen:
            return
        seen.add(id(se))
        if isinstance(se, ShExJ.ShapeDecl):
            self._collect_shape(se.shapeExpr, direct, nested, seen)
        elif isinstance(se, ShExJ.Shape):
            for p in shape_parts(self.cntxt, se):
                if p.expression is not None:
                    self._collect(p.expression, direct, nested, seen, top=False)
        elif isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            for p in se.shapeExprs:
                self._collect_shape(p, direct, nested, seen)


def _is_node_constraint(se) -> bool:
    """A value expression that constrains the node itself, not its arcs."""
    if isinstance(se, ShExJ.NodeConstraint):
        return True
    if isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
        return any(_is_node_constraint(p) for p in se.shapeExprs if not isinstance(p, str))
    if isinstance(se, ShExJ.ShapeNot):
        return _is_node_constraint(se.shapeExpr)
    return False


def _valid_lexical(lexical: str, datatype: str) -> bool | None:
    """Whether rdflib can read ``lexical`` as ``datatype``; None for a datatype it does not know."""
    from rdflib.term import XSDToPython
    dt = URIRef(datatype)
    if dt not in XSDToPython:
        return None
    converter = XSDToPython[dt]
    if converter is None:
        return True
    try:
        converter(lexical)
    except (ValueError, TypeError, ArithmeticError):
        return False
    return True


def _digest(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


def _predicates(expr) -> str:
    """A short name for a triple expression: its first predicate(s)."""
    found = []
    stack = [expr]
    while stack and len(found) < 2:
        e = stack.pop()
        if isinstance(e, ShExJ.TripleConstraint):
            found.append(str(e.predicate))
        elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
            stack.extend(reversed(list(e.expressions)))
    return ", ".join(found) or "(no predicate)"


def _distinct(quads, sources) -> tuple[list, list]:
    """The quads without repeats, and each one's first source."""
    seen, out, prov = set(), [], []
    for q, s in zip(quads, sources):
        if q not in seen:
            seen.add(q)
            out.append(q)
            prov.append(s)
    return out, prov


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
                graph: Graph | None = None, replace: bool = False, **options) -> Graph:
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
    :param replace: with ``graph``, replace what the output schema currently holds at
        ``root`` instead of adding to it (see :meth:`ThreadedMaterializer.update`)
    :raises MaterializationError: when the shape cannot be built
    """
    m = ThreadedMaterializer(schema, prefixes=prefixes, static_vars=static_vars, **options)
    graph = graph if graph is not None else Graph()
    for prefix, ns in m.prefixes.items():
        graph.bind(prefix, ns, override=False)
    if replace:
        m.update(graph, bindings, root, start=start)
        return graph
    for t in m.materialize(bindings, root, start=start):
        graph.add(t)
    return graph
