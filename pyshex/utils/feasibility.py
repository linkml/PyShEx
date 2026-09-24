"""A sound refutation test over partially-determined bags of TripleConstraint matches.

A *partial bag* gives every TripleConstraint TC an interval [lo(TC), hi(TC)]: lo(TC)
triples are committed to TC and at most hi(TC) are attainable.  ``feasible(lo, hi)``
returns False only if **no** bag between lo and hi (pointwise) can be accepted by the
triple expression: it is a necessary condition computable in time linear in the
expression, not a decision procedure -- matches that pass must still be verified by
``matches()``.

Two evaluation modes: in *exact* mode a subexpression must match exactly once, so OneOf
alternatives are exclusive (unchosen branches must be committable to zero) and upper
bounds apply.  In *iterated* mode (under a repeating group cardinality) only the
monotone consequences survive summation over iterations: OneOf branches may mix, upper
bounds vanish, but EachOf co-occurrence survives at the occupancy level.  Deliberately
ignored (left to the exact matcher): count coupling between constraints of a repeated
group, and divisibility.

Ported from the same analysis implemented for Apache Jena
(jena-shex/docs/matching-search-optimization.md, with soundness proof), rudof
(docs/dev/feasibility-model.md) and shex.js (packages/shex-validator/src/feasibility.ts).
"""
from typing import Callable, Optional

from ShExJSG import ShExJ

# Bags are keyed by TripleConstraint object identity (id()); TripleConstraints commonly
# compare equal structurally, which would conflate distinct constraints.
Counts = dict[int, int]

UNBOUNDED = -1


def _min(expr) -> int:
    return expr.min if expr.min is not None else 1


def _max(expr) -> int:
    return expr.max if expr.max is not None else 1


class TripleExprFeasibility:
    """Feasibility analysis for one triple expression."""

    def __init__(self, expr: ShExJ.tripleExpr,
                 lookup_inclusion: Callable[[str], Optional[ShExJ.tripleExpr]]) -> None:
        self.expr = expr
        self.lookup = lookup_inclusion
        #: all TripleConstraints reachable from the expression
        self.triple_constraints: list[ShExJ.TripleConstraint] = []
        self._collect(expr, set())

    def _deref(self, expr, seen: set[str]):
        """Follow tripleExpr references; None signals an (already seen or missing) ref."""
        while not isinstance(expr, (ShExJ.TripleConstraint, ShExJ.EachOf, ShExJ.OneOf)):
            key = str(expr)
            if key in seen:
                return None
            seen.add(key)
            expr = self.lookup(expr)
            if expr is None:
                return None
        return expr

    def _collect(self, expr, seen: set[str]) -> None:
        expr = self._deref(expr, seen)
        if expr is None:
            return
        if isinstance(expr, ShExJ.TripleConstraint):
            self.triple_constraints.append(expr)
        else:
            for nested in expr.expressions:
                self._collect(nested, seen)

    def feasible(self, lo: Counts, hi: Counts) -> bool:
        """Whether some bag c with lo <= c <= hi (pointwise; missing keys are 0) could be
        accepted.  False is definitive; True is not."""
        self._lo, self._hi = lo, hi
        return self._fx(self.expr, set())

    def unattainable_mandatory(self, hi: Counts) -> list[ShExJ.TripleConstraint]:
        """TripleConstraints in mandatory position (not inside a OneOf, no min-0 group
        above) whose predicate has no candidate triples at all: their absence alone makes
        the expression unsatisfiable -- 'missing property' explains a refutation better
        than a generic feasibility error."""
        missing: list[ShExJ.TripleConstraint] = []

        def walk(expr, seen: set[str]) -> None:
            expr = self._deref(expr, seen)
            if expr is None or _min(expr) == 0:
                return
            if isinstance(expr, ShExJ.TripleConstraint):
                if hi.get(id(expr), 0) == 0:
                    missing.append(expr)
            elif isinstance(expr, ShExJ.EachOf):
                for nested in expr.expressions:
                    walk(nested, seen)
            # OneOf: no single branch is mandatory

        walk(self.expr, set())
        return missing

    # -- internals ---------------------------------------------------------------

    def _get_lo(self, tc) -> int:
        return self._lo.get(id(tc), 0)

    def _get_hi(self, tc) -> int:
        return self._hi.get(id(tc), 0)

    def _zero(self, expr, seen: set[str]) -> bool:
        """The subexpression's slice can be committed to all-zero."""
        expr = self._deref(expr, seen)
        if expr is None:
            return True
        if isinstance(expr, ShExJ.TripleConstraint):
            return self._get_lo(expr) == 0
        return all(self._zero(nested, seen) for nested in expr.expressions)

    def _fx(self, expr, seen: set[str]) -> bool:
        """Exact mode: necessary condition for the slice to be accepted exactly once."""
        expr = self._deref(expr, seen)
        if expr is None:
            return True
        if isinstance(expr, ShExJ.TripleConstraint):
            mn, mx = _min(expr), _max(expr)
            return (mx == UNBOUNDED or self._get_lo(expr) <= mx) and self._get_hi(expr) >= mn
        mn, mx = _min(expr), _max(expr)
        if mx == 0:
            return self._zero(expr, set(seen))
        if mn == 0 and mx == 1:                                  # ?
            return self._zero(expr, set(seen)) or self._fx_body(expr, seen)
        if mn == 1 and mx == 1:                                  # exactly once
            return self._fx_body(expr, seen)
        if mn == 0:                                              # * or {0,n}
            return self._zero(expr, set(seen)) or (self._fi_body(expr, seen) and self._once(expr, seen))
        # min >= 1 with repetition: any accepted slice is a sum of >= 1 iteration bags
        return self._fi_body(expr, seen) and self._once(expr, seen)

    def _fx_body(self, expr, seen: set[str]) -> bool:
        if isinstance(expr, ShExJ.EachOf):
            return all(self._fx(nested, seen) for nested in expr.expressions)
        # OneOf, exact: one branch matches, the others' slices are zero
        return any(self._fx(branch, seen)
                   and all(self._zero(other, set(seen))
                           for j, other in enumerate(expr.expressions) if j != i)
                   for i, branch in enumerate(expr.expressions))

    def _fi(self, expr, seen: set[str]) -> bool:
        """Iterated mode: the slice is a sum of >= 1 iteration bags (monotone weakening)."""
        expr = self._deref(expr, seen)
        if expr is None:
            return True
        if isinstance(expr, ShExJ.TripleConstraint):
            mn, mx = _min(expr), _max(expr)
            return (mn == 0 or self._get_hi(expr) >= mn) and (mx != 0 or self._get_lo(expr) == 0)
        mn, mx = _min(expr), _max(expr)
        if mx == 0:
            return self._zero(expr, set(seen))
        if mn == 0:
            return self._zero(expr, set(seen)) or self._fi_body(expr, seen)
        return self._fi_body(expr, seen) and self._once(expr, seen)

    def _fi_body(self, expr, seen: set[str]) -> bool:
        if isinstance(expr, ShExJ.EachOf):
            return all(self._fi(nested, seen) for nested in expr.expressions)
        # OneOf, iterated: branches may mix; an occupied branch must itself be iterable
        return all(self._zero(branch, set(seen)) or self._fi(branch, seen)
                   for branch in expr.expressions)

    def _once(self, expr, seen: set[str]) -> bool:
        """Occupancy of one non-empty iteration within hi."""
        expr = self._deref(expr, seen)
        if expr is None:
            return True
        if isinstance(expr, ShExJ.TripleConstraint):
            mn = _min(expr)
            return mn == 0 or self._get_hi(expr) >= mn
        if _min(expr) == 0:
            return True
        if isinstance(expr, ShExJ.EachOf):
            return all(self._once(nested, seen) for nested in expr.expressions)
        return any(self._once(nested, seen) for nested in expr.expressions)


def predicate_counts(feasibility: TripleExprFeasibility, matchables) -> Counts:
    """hi bag: for each TripleConstraint, the number of matchable triples with its
    predicate (in the right direction).  Over-approximates any partition's share, which
    keeps refutation sound; value expressions are not consulted (cheap and still sound)."""
    hi: Counts = {}
    for tc in feasibility.triple_constraints:
        pred = str(tc.predicate)
        n = sum(1 for t in matchables if str(t.p) == pred)
        if n:
            hi[id(tc)] = n
    return hi
