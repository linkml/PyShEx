""" Implementation of `5.5 Shapes and Triple Expressions <http://shex.io/shex-semantics/#shapes-and-TEs>`_"""
from ShExJSG import ShExJ
from pyjsg.jsglib import isinstance_
from rdflib import URIRef
from sparqlslurper import SlurpyGraph

from pyshex.shape_expressions_language.p3_terminology import arcsOut
from pyshex.shape_expressions_language.p5_7_semantic_actions import semActsSatisfied
from pyshex.shape_expressions_language.p5_context import Context, DebugContext
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph, RDFTriple, Node
from itertools import product

from pyshex.utils.feasibility import TripleExprFeasibility, predicate_counts
from pyshex.utils.matchesEachOfEvaluator import EachOfEvaluator
from pyshex.utils.partitions import partition_t, partition_2
from pyshex.utils.schema_utils import predicates_in_expression, triple_constraints_in_expression, \
    directed_predicates_in_expression
from pyshex.utils.slurp_utils import slurper
from pyshex.utils.trace_utils import trace_matches, trace_satisfies, trace_matches_tripleconstraint
from pyshex.utils.value_set_utils import uriref_matches_iriref, iriref_to_uriref


@trace_satisfies()
def satisfiesShape(cntxt: Context, n: Node, S: ShExJ.Shape, c: DebugContext) -> bool:
    """ `5.5.2 Semantics <http://shex.io/shex-semantics/#triple-expressions-semantics>`_

    For a node `n`, shape `S`, graph `G`, and shapeMap `m`, `satisfies(n, S, G, m)` if and only if:

    * `neigh(G, n)` can be partitioned into two sets matched and remainder such that
      `matches(matched, expression, m)`. If expression is absent, remainder = `neigh(G, n)`.

    :param n: focus node
    :param S: Shape to be satisfied
    :param cntxt: Evaluation context
    :param c: Debug context
    :return: true iff `satisfies(n, S, cntxt)`
    """

    # Recursion detection.  If start_evaluating returns a boolean value, this is the assumed result of the shape
    # evaluation.  If it returns None, then an initial evaluation is needed.
    # Evaluations against an EXTENDS-allocated part of the neighbourhood are not cached
    # and consult no cache: the same (node, shape) pair can genuinely differ between
    # parts (cf. shex.js, which skips its "known"/"seen" caches under a subGraph).
    restricted = _active_restriction(cntxt, n) is not None
    rslt = None if restricted else cntxt.start_evaluating(n, S)

    if rslt is None:
        cntxt.evaluate_stack.append((n, S.id))

        if getattr(S, 'extends', None):
            rslt = satisfiesExtendedShape(cntxt, n, S, c)
            if not restricted:
                done, consistent = cntxt.done_evaluating(n, S, rslt)
                if not done:
                    rslt = satisfiesShape(cntxt, n, S)
                rslt = rslt and consistent
            cntxt.evaluate_stack.pop()
            return rslt

        predicates = directed_predicates_in_expression(S, cntxt)
        matchables = _collect_matchables(cntxt, n, S, predicates)

        if c.debug:
            print(c.i(1, "predicates:", sorted(cntxt.n3_mapper.n3(p) for p in predicates.keys())))
            print(c.i(1, "matchables:", sorted(cntxt.n3_mapper.n3(m) for m in matchables)))
            print()

        if S.closed:
            # TODO: Is this working correctly on reverse items?
            restriction = _active_restriction(cntxt, n)
            base = restriction if restriction is not None else arcsOut(cntxt.graph, n)
            non_matchables = RDFGraph([t for t in base if t not in matchables])
            if len(non_matchables):
                cntxt.fail_reason = "Unmatched triples in CLOSED shape:"
                cntxt.fail_reason = '\n'.join(f"\t{t}" for t in non_matchables)
                if c.debug:
                    print(c.i(0,
                              f"<--- Satisfies shape {c.d()} FAIL - "
                              f"{len(non_matchables)} non-matching triples on a closed shape"))
                    print(c.i(1, "", list(non_matchables)))
                    print()
                return False

        # Evaluate the actual expression.  Start assuming everything matches...
        if S.expression:
            rslt = _expression_matches(cntxt, matchables, S, c)
        else:
            rslt = True         # Empty shape

        # If an assumption was made and the result doesn't match the assumption, switch directions and try again
        if not restricted:
            done, consistent = cntxt.done_evaluating(n, S, rslt)
            if not done:
                rslt = satisfiesShape(cntxt, n, S)
            rslt = rslt and consistent

        cntxt.evaluate_stack.pop()
    return rslt


def _restriction_stack(cntxt: Context) -> list:
    if not hasattr(cntxt, '_extends_restrictions'):
        cntxt._extends_restrictions = []
    return cntxt._extends_restrictions


def _active_restriction(cntxt: Context, n: Node) -> RDFGraph | None:
    """The set of triples an enclosing EXTENDS allocation dedicated to evaluations of
    node n, if any.  Scoped by focus node so that value expression evaluation of other
    nodes still sees the whole graph."""
    for node, triples in reversed(_restriction_stack(cntxt)):
        if node == n:
            return triples
    return None


def _collect_matchables(cntxt: Context, n: Node, S: ShExJ.Shape, predicates) -> RDFGraph:
    """The neighbourhood triples whose predicate is mentioned in the expression --
    from the enclosing EXTENDS allocation when one is active, otherwise from the graph."""
    matchables = RDFGraph()
    restriction = _active_restriction(cntxt, n)
    if restriction is not None:
        for t in restriction:
            direction = predicates.get(str(t.p))
            if direction is not None and ((direction.is_fwd and t.s == n) or (direction.is_rev and t.o == n)):
                matchables.add(t)
        return matchables

    # Note: The code below does an "over-slurp" for the sake of expediency.  If you are interested in
    #       getting EXACTLY the needed triples, set cntxt.over_slurp to false
    if isinstance(cntxt.graph, SlurpyGraph) and cntxt.over_slurp:
        with slurper(cntxt, n, S) as g:
            _ = g.triples((n, None, None))

    for predicate, direction in predicates.items():
        with slurper(cntxt, n, S) as g:
            matchables.add_triples(g.triples((n if direction.is_fwd else None,
                                              iriref_to_uriref(predicate),
                                              n if direction.is_rev else None)))
    return matchables


def _expression_matches(cntxt: Context, matchables: RDFGraph, S: ShExJ.Shape, c: DebugContext) -> bool:
    """Evaluate S.expression against matchables, honoring EXTRA -- with a feasibility
    guard that refutes structurally hopeless neighbourhoods before any partitioning."""
    feas = TripleExprFeasibility(S.expression, cntxt.tripleExprFor)
    hi = predicate_counts(feas, matchables)
    if not feas.feasible({}, hi):
        missing = feas.unattainable_mandatory(hi)
        if missing:
            # Same wording as the cardinality check this guard pre-empts, so that a
            # refutation reads identically whether it was found early or by matching.
            cntxt.fail_reason = '\n'.join(
                f"   No matching triples found for predicate {p}" for p in
                dict.fromkeys(cntxt.n3_mapper.n3(iriref_to_uriref(tc.predicate)) for tc in missing))
        else:
            cntxt.fail_reason = "Feasibility: no assignment of the neighbourhood can satisfy the expression"
        return False

    extras = {iriref_to_uriref(e) for e in S.extra} if S.extra is not None else {}
    if matches(cntxt, matchables, S.expression, extras):
        return True
    if len(extras):
        permutable_matchables = RDFGraph([t for t in matchables if t.p in extras])
        non_permutable_matchables = RDFGraph([t for t in matchables if t not in permutable_matchables])
        if c.debug:
            print(c.i(1, f"Complete match failed -- evaluating extras", list(extras)))
        for matched, remainder in partition_2(permutable_matchables):
            permutation = non_permutable_matchables.union(matched)
            # feasibility pre-filter: skip subsets that cannot satisfy the expression
            if not feas.feasible({}, predicate_counts(feas, permutation)):
                continue
            if matches(cntxt, permutation, S.expression):
                return True
    return False


def _candidate_predicates(cntxt: Context, se) -> dict:
    """Directed predicates that could allocate triples to an extension target: the
    predicates of every Shape reachable through references, AND/OR branches and extends
    chains.  Negated shape expressions contribute none -- a negation is a filter over
    the allocated triples, never a sink for them (cf. the Jena/rudof/shex.js EXTENDS
    implementations)."""
    result: dict = {}
    seen: set[int] = set()

    def walk(expr) -> None:
        if expr is None or id(expr) in seen:
            return
        seen.add(id(expr))
        if isinstance_(expr, ShExJ.shapeExprLabel):
            walk(cntxt.shapeExprFor(expr))
        elif isinstance(expr, ShExJ.ShapeDecl):
            walk(expr.shapeExpr)
        elif isinstance(expr, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            for nested in expr.shapeExprs:
                walk(nested)
        elif isinstance(expr, ShExJ.Shape):
            for pred, direction in directed_predicates_in_expression(expr, cntxt).items():
                merged = result.setdefault(pred, type(direction)())
                if direction.is_fwd:
                    merged.dir(True)
                if direction.is_rev:
                    merged.dir(False)
            for ext in getattr(expr, 'extends', None) or []:
                walk(ext)
        # ShapeNot, NodeConstraint, ShapeExternal: no candidate predicates

    walk(se)
    return result


def _extension_triple_constraints(cntxt: Context, se) -> list:
    """The TripleConstraints reachable from an extension target through references,
    AND/OR branches, shapes' expressions and their extends chains.  Negated shape
    expressions contribute none (a negation is a filter, not a sink)."""
    result: list = []
    seen: set[int] = set()

    def tc_collector(acc, expr, _cntxt) -> None:
        if isinstance(expr, ShExJ.TripleConstraint):
            acc.append(expr)

    def walk(expr) -> None:
        if expr is None or id(expr) in seen:
            return
        seen.add(id(expr))
        if isinstance_(expr, ShExJ.shapeExprLabel):
            walk(cntxt.shapeExprFor(expr))
        elif isinstance(expr, ShExJ.ShapeDecl):
            walk(expr.shapeExpr)
        elif isinstance(expr, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            for nested in expr.shapeExprs:
                walk(nested)
        elif isinstance(expr, ShExJ.Shape):
            if expr.expression is not None:
                cntxt.visit_triple_expressions(expr.expression, tc_collector, result)
            for ext in getattr(expr, 'extends', None) or []:
                walk(ext)

    walk(se)
    return result


def satisfiesExtendedShape(cntxt: Context, n: Node, S: ShExJ.Shape, c: DebugContext) -> bool:
    """satisfies(n, S) for a Shape with extends: some allocation of the matchable
    neighbourhood among the extension targets and the local expression is such that each
    extension target is satisfied by n with its allocated triples (evaluated through the
    ordinary satisfies(), so OR / AND / NOT parents work uniformly) and the local
    expression matches its allocated triples."""
    from pyshex.shape_expressions_language.p5_3_shape_expressions import satisfies

    ext_exprs = [cntxt.shapeExprFor(e) if isinstance_(e, ShExJ.shapeExprLabel) else e for e in S.extends]
    ext_preds = [_candidate_predicates(cntxt, se) for se in ext_exprs]
    local_preds = directed_predicates_in_expression(S, cntxt) if S.expression else {}
    local_ix = len(ext_exprs)

    # Selection-local matchables: the union of the extension targets' and the local
    # expression's predicates
    all_preds: dict = {}
    for preds in ext_preds + [local_preds]:
        for pred, direction in preds.items():
            merged = all_preds.setdefault(pred, type(direction)())
            if direction.is_fwd:
                merged.dir(True)
            if direction.is_rev:
                merged.dir(False)
    matchables = _collect_matchables(cntxt, n, S, all_preds)

    if S.closed:
        restriction = _active_restriction(cntxt, n)
        base = restriction if restriction is not None else arcsOut(cntxt.graph, n)
        non_matchables = RDFGraph([t for t in base if t not in matchables])
        if len(non_matchables):
            cntxt.fail_reason = "Unmatched triples in CLOSED shape:"
            cntxt.fail_reason = '\n'.join(f"\t{t}" for t in non_matchables)
            return False

    def eligible_dir(t, preds) -> bool:
        direction = preds.get(str(t.p))
        return direction is not None and ((direction.is_fwd and t.s == n) or (direction.is_rev and t.o == n))

    # Allocation is to *triple constraints*, and a constraint reached through several
    # extension chains (diamond inheritance: a shared ancestor) allocates its triples to
    # every one of those extensions at once -- a triple cannot evade one chain's
    # constraints by hiding in another (cf. shex.js tc2exts).  Eligibility checks the
    # value expression as well as the predicate, so e.g. a role a NOT-ed shape rejects
    # is never allocated on the strength of that shape's constraint.
    tc2exts: dict[int, set[int]] = {}
    all_tcs: dict[int, ShExJ.TripleConstraint] = {}
    for i, se in enumerate(ext_exprs):
        for tc in _extension_triple_constraints(cntxt, se):
            tc2exts.setdefault(id(tc), set()).add(i)
            all_tcs[id(tc)] = tc

    def tc_eligible(t, tc) -> bool:
        if str(t.p) != str(tc.predicate):
            return False
        if tc.inverse and t.o != n or not tc.inverse and t.s != n:
            return False
        return matchesTripleConstraint(cntxt, t, tc)

    extras = {iriref_to_uriref(e) for e in S.extra} if S.extra is not None else {}
    alloc_triples = []
    candidates: list[list[tuple[int, ...]]] = []
    for t in sorted(matchables):
        signatures = {tuple(sorted(tc2exts[key])) for key, tc in all_tcs.items() if tc_eligible(t, tc)}
        options: list[tuple[int, ...]] = sorted(signatures)
        if S.expression and eligible_dir(t, local_preds):
            options.append((local_ix,))
        if not options:
            if t.p in extras:
                continue        # absorbed by EXTRA
            cntxt.fail_reason = f"EXTENDS: triple {t} matches no extension target or local expression"
            return False
        alloc_triples.append(t)
        candidates.append(options)

    feas = TripleExprFeasibility(S.expression, cntxt.tripleExprFor) if S.expression else None
    ext_memo: dict = {}         # (extension ordinal, allocated triples) -> bool

    for assignment in product(*candidates):
        parts: list[RDFGraph] = [RDFGraph() for _ in range(len(ext_exprs) + 1)]
        for t, targets in zip(alloc_triples, assignment):
            for target in targets:
                parts[target].add(t)

        # feasibility guard: refute the local part before any evaluation
        if feas is not None and not feas.feasible({}, predicate_counts(feas, parts[local_ix])):
            continue

        ok = True
        for i, se in enumerate(ext_exprs):
            key = (i, frozenset(parts[i]))
            if key not in ext_memo:
                _restriction_stack(cntxt).append((n, parts[i]))
                try:
                    ext_memo[key] = satisfies(cntxt, n, se)
                finally:
                    _restriction_stack(cntxt).pop()
            if not ext_memo[key]:
                ok = False
                break
        if ok and S.expression:
            ok = _expression_matches(cntxt, parts[local_ix], S, c)
        if ok:
            return True

    cntxt.fail_reason = (f"EXTENDS: no allocation of {len(alloc_triples)} triple(s) to "
                         f"{len(ext_exprs)} extension(s) and the local expression satisfies all parts")
    return False


def valid_remainder(cntxt: Context, n: Node, matchables: RDFGraph, S: ShExJ.Shape) -> bool:
    """
    Let **outs** be the arcsOut in remainder: `outs = remainder ∩ arcsOut(G, n)`.

    Let **matchables** be the triples in outs whose predicate appears in a TripleConstraint in `expression`. If
    `expression` is absent, matchables = Ø (the empty set).

    * There is no triple in **matchables** which matches a TripleConstraint in expression

    * There is no triple in **matchables** whose predicate does not appear in extra.

    * closed is false or unmatchables is empty

    :param cntxt: evaluation context
    :param n: focus node
    :param matchables: non-matched triples
    :param S: Shape being evaluated
    :return: True if remainder is valid
    """
    # TODO: Update this and satisfies to address the new algorithm
    # Let **outs** be the arcsOut in remainder: `outs = remainder ∩ arcsOut(G, n)`.
    outs = arcsOut(cntxt.graph, n).intersection(matchables)

    # predicates that in a TripleConstraint in `expression`
    predicates = predicates_in_expression(S, cntxt)

    # Let **matchables** be the triples in outs whose predicate appears in predicates. If
    # `expression` is absent, matchables = Ø (the empty set).
    matchables = RDFGraph(t for t in outs if str(t.p) in predicates)

    # There is no triple in **matchables** which matches a TripleConstraint in expression
    if matchables and S.expression is not None:
        tes = triple_constraints_in_expression(S.expression, cntxt)
        for m in matchables:
            if any(matchesTripleConstraint(cntxt, m, te) for te in tes):
                return False

    # There is no triple in **matchables** whose predicate does not appear in extra.
    extras = {iriref_to_uriref(e) for e in S.extra} if S.extra is not None else {}
    if any(t.p not in extras for t in matchables):
        return False

    # closed is false or unmatchables is empty.
    return not S.closed.val or not bool(outs - matchables)


def matches(cntxt: Context, T: RDFGraph, expr: ShExJ.tripleExpr, extras: set[URIRef] | None = None) -> bool:
    """
    **matches**: asserts that a triple expression is matched by a set of triples that come from the neighbourhood of a
    node in an RDF graph. The expression `matches(T, expr, m)` indicates that a set of triples `T` can satisfy these
    rules:

    extras is a hint that, if present, can be used to bypass cardinality permutations.  Beware, however, that this
    may make the semantic actions more complex.

    * expr has semActs and `matches(T, expr, m)` by the remaining rules in this list and the evaluation
      of semActs succeeds according to the section below on Semantic Actions.
    * expr has a cardinality of min and/or max not equal to 1, where a max of -1 is treated as unbounded, and T
      can be partitioned into k subsets T1, T2,…Tk such that min ≤ k ≤ max and for each Tn,
      `matches(Tn, expr, m)` by the remaining rules in this list.
    * expr is a OneOf and there is some shape expression se2 in shapeExprs such that a matches(T, se2, m).
    * expr is an EachOf and there is some partition of T into T1, T2,… such that for every expression
      expr1, expr2,… in shapeExprs, matches(Tn, exprn, m).
    * expr is a TripleConstraint and:
        * T is a set of one triple. Let t be the soul triple in T.
        * t's predicate equals expr's predicate. Let value be t's subject if inverse is true, else t's object.
        * if inverse is true, t is in arcsIn, else t is in `arcsOut`.
        * either
            * expr has no valueExpr
            * or `satisfies(value, valueExpr, G, m).
    """
    if isinstance_(expr, ShExJ.tripleExprLabel):
        return matchesExpr(cntxt, T, expr)
    else:
        return matchesCardinality(cntxt, T, expr, extras) \
               and (expr.semActs is None or semActsSatisfied(expr.semActs, cntxt))


@trace_matches(True)
def matchesTripleExprLabel(cntxt: Context, T: RDFGraph, expr: ShExJ.tripleExprLabel, c: DebugContext) -> bool:
    if c.debug:
        print(f" {expr}")
    te = cntxt.tripleExprFor(expr)
    if te:
        return matchesCardinality(cntxt, T, te)
    cntxt.fail_reason = f"{expr}: Labeled triple expression not found"
    return False


@trace_matches(False)
def matchesCardinality(cntxt: Context, T: RDFGraph, expr: ShExJ.tripleExpr | ShExJ.tripleExprLabel,
                       c: DebugContext, extras: set[URIRef] | None = None) -> bool:
    """ Evaluate cardinality expression

    expr has a cardinality of min and/or max not equal to 1, where a max of -1 is treated as unbounded, and
    T can be partitioned into k subsets T1, T2,…Tk such that min ≤ k ≤ max and for each Tn,
    matches(Tn, expr, m) by the remaining rules in this list.
    """
    # TODO: Cardinality defaults into spec
    min_ = expr.min if expr.min is not None else 1
    max_ = expr.max if expr.max is not None else 1

    cardinality_text = f"{{{min_},{'*' if max_ == -1 else max_}}}"
    if c.debug and (min_ != 0 or len(T) != 0):
        print(f"{cardinality_text} matching {len(T)} triples")
    if min_ == 0 and len(T) == 0:
        return True
    if isinstance(expr, ShExJ.TripleConstraint):
        if len(T) < min_:
            if len(T) > 0:
                _fail_triples(cntxt, T)
                cntxt.fail_reason = f"   {len(T)} triples less than {cardinality_text}"
            else:
                cntxt.fail_reason = f"   No matching triples found for predicate {cntxt.n3_mapper.n3(expr.predicate)}"
            return False

        # Don't include extras in the cardinality check
        if extras:
            must_match = RDFGraph([t for t in T if t.p not in extras])  # The set of things NOT consumed in extra
        else:
            must_match = T
        if 0 <= max_ < len(must_match):
            # Don't do a cardinality check
            _fail_triples(cntxt, T)
            cntxt.fail_reason = f"   {len(T)} triples exceeds max {cardinality_text}"
            return False
        elif len(must_match):
            return all(matchesTripleConstraint(cntxt, t, expr) for t in must_match)
        else:
            return any(matchesTripleConstraint(cntxt, t, expr) for t in T)
    else:
        for partition in _partitions(T, min_, max_):
            if all(matchesExpr(cntxt, part, expr) for part in partition):
                return True
        if min_ != 1 or max_ != 1:
            _fail_triples(cntxt, T)
            cntxt.fail_reason = f"   {len(T)} triples cannot be partitioned into {cardinality_text} passing groups"
        return False


def _fail_triples(cntxt: Context, T: RDFGraph) -> None:
    tlist = list(T)
    if len(tlist):
        cntxt.fail_reason = "Triples:"
        for t in sorted(tlist):
            cntxt.fail_reason = f"      {cntxt.n3_mapper.n3(t)}"
        if len(tlist) > 5:
            cntxt.fail_reason = "      ...   "


def _partitions(T: RDFGraph, min_: int | None, max_: int | None) -> list[list[RDFGraph]]:
    if max_ == 1:
        yield [T]
    else:
        for k in range(max(min_, 1), (max(len(T), min_) if max_ == -1 else max_)+1):
            for partition in partition_t(T, k):
                yield partition


@trace_matches()
def matchesExpr(cntxt: Context, T: RDFGraph, expr: ShExJ.tripleExpr, _: DebugContext) -> bool:
    """ Evaluate the expression

    """

    if isinstance(expr, ShExJ.OneOf):
        return matchesOneOf(cntxt, T, expr)
    elif isinstance(expr, ShExJ.EachOf):
        return matchesEachOf(cntxt, T, expr)
    elif isinstance(expr, ShExJ.TripleConstraint):
        return matchesCardinality(cntxt, T, expr)
    elif isinstance_(expr, ShExJ.tripleExprLabel):
        return matchesTripleExprRef(cntxt, T, expr)
    else:
        raise Exception("Unknown expression")


@trace_matches()
def matchesOneOf(cntxt: Context, T: RDFGraph, expr: ShExJ.OneOf, _: DebugContext) -> bool:
    """
    expr is a OneOf and there is some shape expression se2 in shapeExprs such that a matches(T, se2, m).
    """
    return any(matches(cntxt, T, e) for e in expr.expressions)


@trace_matches()
def matchesEachOf(cntxt: Context, T: RDFGraph, expr: ShExJ.EachOf, _: DebugContext) -> bool:
    """ expr is an EachOf and there is some partition of T into T1, T2,… such that for every expression
     expr1, expr2,… in shapeExprs, matches(Tn, exprn, m).
     """

    return EachOfEvaluator(cntxt, T, expr).evaluate(cntxt)


@trace_matches_tripleconstraint()
def matchesTripleConstraint(cntxt: Context, t: RDFTriple, expr: ShExJ.TripleConstraint, c: DebugContext) -> bool:
    """
    expr is a TripleConstraint and:

    * t is a triple
    * t's predicate equals expr's predicate.
      Let value be t's subject if inverse is true, else t's object.
    * if inverse is true, t is in arcsIn, else t is in arcsOut.

    """
    from pyshex.shape_expressions_language.p5_3_shape_expressions import satisfies

    if c.debug:
        print(c.i(1, f" triple: {t}"))
        print(c.i(1, '', expr._as_json_dumps().split('\n')))

    if uriref_matches_iriref(t.p, expr.predicate):
        value = t.s if expr.inverse else t.o
        return expr.valueExpr is None or satisfies(cntxt, value, expr.valueExpr)
    else:
        cntxt.fail_reason = f"Predicate mismatch: {t.p} ≠ {expr.predicate}"
        return False


@trace_matches()
def matchesTripleExprRef(cntxt: Context, T: RDFGraph, expr: ShExJ.tripleExprLabel, _: DebugContext) -> bool:
    """
    expr is an tripleExprRef and satisfies(value, tripleExprWithId(tripleExprRef), G, m).
    The tripleExprWithId function is defined in Triple Expression Reference Requirement below.
    """
    tefor_expr = cntxt.tripleExprFor(expr)
    if tefor_expr is None:
        cntxt.fail_reason = f"{expr}: Reference not found"
        return False
    return matchesExpr(cntxt, T, tefor_expr)
