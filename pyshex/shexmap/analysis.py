"""Static checks of a ShExMap schema pair, before any data.

Given the input schema and the output schema, :func:`analyse` says whether every output
repetition has a well-formed iteration scope, whether every variable the output reads is
bound in the input where it can be read from, and which bindings go unused -- the questions
materialization would otherwise answer at run time, one graph at a time.  The checks are
the schema-pair conditions XSugar and biXid impose on grammar pairs, and the
"updatability" question of the view-update literature, in ShExMap's terms; see
``docs/shexmap-structural-plan.md`` §4 phase 3.

A variable's **site** is the chain of repeated constraints and groups of the input schema
that enclose its ``%Map`` code: it is bound once per iteration of the innermost one, or once
for the whole tree when the chain is empty.  An output repetition's **iteration scope** is
the deepest site among the variables its body reads, nested repetitions counting through
their parent site; it is ill-formed when two of those sites lie in unrelated lists.  A
constraint may read a variable whose site is an ancestor of (or equal to) the scope it is
evaluated at; a deeper site means "which one?", and an unrelated one means the value is
not in scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ShExJSG import ShExJ

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.shexmap import functions
from pyshex.shexmap.bindings import (declaration_of, expression_of, extension_candidates, is_repeated, map_actions,
                                     references_shape, shape_parts, shexc_prefixes)

Site = tuple[int, ...]              # ids of the enclosing repeated expressions, outermost first


@dataclass
class Report:
    """What :func:`analyse` found.  ``errors`` make the pair not mappable; ``warnings`` do not.
    Messages write IRIs with the schemas' prefixes."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bound: dict[str, Site] = field(default_factory=dict)        # input variable -> site
    read: set[str] = field(default_factory=set)                 # variables the output reads
    labels: dict[int, str] = field(default_factory=dict)        # repeated expression id -> name
    prefixes: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def where(self, site: Site) -> str:
        return "the root" if not site else "each " + " / ".join(self.labels.get(i, "?") for i in site)

    def short(self, text: str) -> str:
        """``text`` with every namespace the schemas declare written as its prefix."""
        for prefix, ns in sorted(self.prefixes.items(), key=lambda kv: -len(kv[1])):
            if ns:
                text = text.replace(ns, prefix + ":")
        return text

    def error(self, message: str) -> None:
        self.errors.append(self.short(message))

    def warn(self, message: str) -> None:
        self.warnings.append(self.short(message))

    def __str__(self) -> str:
        lines = [f"error: {e}" for e in self.errors] + [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "ok: the schemas map coherently"


def analyse(input_schema, output_schema, prefixes=None, input_start=None, output_start=None,
            static_vars=()) -> Report:
    """Check that ``output_schema`` can be materialized coherently from what ``input_schema`` binds.

    :param input_schema: ShExC text or a parsed ShExJ schema
    :param output_schema: ShExC text or a parsed ShExJ schema
    :param prefixes: prefixes for ShExMap variable names; read from ShExC texts when omitted
    :param input_start, output_start: shape labels; default the schemas' start shapes
    :param static_vars: variable IRIs that will be supplied as static variables
    """
    from pyshex.utils.schema_loader import SchemaLoader
    prefixes = dict(prefixes or {})
    schemas = []
    for text in (input_schema, output_schema):
        if isinstance(text, str):
            prefixes = {**shexc_prefixes(text), **prefixes}
            schema = SchemaLoader().loads(text)
            if schema is None:
                raise ValueError("a schema does not parse")
        else:
            schema = text
        schemas.append(schema)
    report = Report(prefixes=prefixes)
    inp = _Input(Context(None, schemas[0]), prefixes, report)
    inp.run(_start(schemas[0], input_start))
    out = _Output(Context(None, schemas[1]), prefixes, report, set(static_vars))
    out.run(_start(schemas[1], output_start))
    for v, site in report.bound.items():
        if v not in report.read:
            report.warn(f"{v} is bound (at {report.where(site)}) but the output never reads it")
    for v in sorted(set(static_vars) - report.read):
        report.warn(f"static variable {v} is never read")
    return report


def _start(schema, start):
    if start is None or start is START:
        if schema.start is None:
            raise ValueError("the schema has no start shape; name one")
        return schema.start
    return ShExJ.IRIREF(str(start))


def _is_repetition(expr) -> bool:
    """Any cardinality but exactly one, as the materializer treats it (``?`` included)."""
    return not (expr.min in (None, 1) and expr.max in (None, 1))


def _label(expr) -> str:
    found: list[str] = []
    stack = [expr]
    while stack and len(found) < 2:
        e = stack.pop()
        if isinstance(e, ShExJ.TripleConstraint):
            found.append(("^" if e.inverse else "") + str(e.predicate))
        elif isinstance(e, (ShExJ.EachOf, ShExJ.OneOf)):
            stack.extend(reversed(list(e.expressions)))
    return "(" + ", ".join(found) + ")" if len(found) > 1 else (found[0] if found else "(group)")


def _variables(tc, prefixes) -> tuple[list[str], list[str]]:
    """(variables bound or read by a constraint's Map codes, id() arguments) -- id() is not a
    variable code; its arguments are returned apart."""
    plain: list[str] = []
    keys: list[str] = []
    for act in map_actions(tc):
        code = str(act.code or '')
        try:
            if functions.is_key_code(code):
                keys.extend(a for a in functions.key_arguments(code, prefixes) if a != functions.NODE_ARGUMENT)
            elif functions.is_function_call(code):
                plain.extend(functions.variables_of(code, prefixes))
            else:
                plain.append(functions.expand_variable(code, prefixes))
        except functions.MapFunctionError:
            pass
    return plain, keys


class _Input:
    """Where the input schema binds each variable."""

    def __init__(self, cntxt: Context, prefixes, report: Report) -> None:
        self.cntxt, self.prefixes, self.report = cntxt, prefixes, report
        self.seen: set[int] = set()

    def run(self, se) -> None:
        self.shape_expr(se, ())

    def shape_expr(self, se, site: Site) -> None:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                return
            for o in extension_candidates(self.cntxt, decl):
                self.shape_expr(expression_of(o), site)
            return
        if id(se) in self.seen:
            return
        self.seen.add(id(se))
        if isinstance(se, ShExJ.ShapeDecl):
            self.shape_expr(se.shapeExpr, site)
        elif isinstance(se, ShExJ.Shape):
            for p in shape_parts(self.cntxt, se):
                if p.expression is not None:
                    self.expression(p.expression, site)
        elif isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            for p in se.shapeExprs:
                self.shape_expr(p, site)

    def expression(self, expr, site: Site) -> None:
        if isinstance(expr, str):
            expr = self.cntxt.tripleExprFor(expr)
        if expr is None:
            return
        if is_repeated(expr):
            self.report.labels[id(expr)] = _label(expr)
            site = site + (id(expr),)
        if isinstance(expr, ShExJ.TripleConstraint):
            plain, _ = _variables(expr, self.prefixes)
            for v in plain:
                at = self.report.bound.setdefault(v, site)
                if at != site:
                    self.report.error(
                        f"{v} is bound at two places of the input schema, {self.report.where(at)} and "
                        f"{self.report.where(site)}; a variable must have one binding site")
            if references_shape(expr.valueExpr):
                self.shape_expr(expr.valueExpr, site)
        elif isinstance(expr, (ShExJ.EachOf, ShExJ.OneOf)):
            for e in expr.expressions:
                self.expression(e, site)


class _Output:
    """Where the output schema reads each variable, and what each repetition iterates."""

    def __init__(self, cntxt: Context, prefixes, report: Report, statics: set[str]) -> None:
        self.cntxt, self.prefixes, self.report, self.statics = cntxt, prefixes, report, statics
        self.scopes: dict[int, Site | None] = {}
        self.ill_formed: set[int] = set()
        self.active: set[int] = set()

    def run(self, se) -> None:
        self.shape_expr(se, ())

    # -- walking ------------------------------------------------------------------------
    def shape_expr(self, se, scope: Site) -> None:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                self.report.error(f"the output schema references {se}, which it does not define")
                return
            options = extension_candidates(self.cntxt, decl)
            if not options:
                self.report.error(f"{se} is abstract and nothing extends it")
            for o in options:
                self.shape_expr(expression_of(o), scope)
            return
        key = id(se)
        if key in self.active:
            return                          # a recursive shape: the first pass covered it
        self.active.add(key)
        try:
            if isinstance(se, ShExJ.ShapeDecl):
                self.shape_expr(se.shapeExpr, scope)
            elif isinstance(se, ShExJ.Shape):
                for p in shape_parts(self.cntxt, se):
                    if p.expression is not None:
                        self.expression(p.expression, scope)
            elif isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
                for p in se.shapeExprs:
                    if not isinstance(p, ShExJ.NodeConstraint):
                        self.shape_expr(p, scope)
            elif isinstance(se, ShExJ.NodeConstraint):
                pass
            else:
                self.report.error(f"{type(se).__name__} cannot be materialized")
        finally:
            self.active.discard(key)

    def expression(self, expr, scope: Site) -> None:
        if isinstance(expr, str):
            expr = self.cntxt.tripleExprFor(expr)
        if expr is None:
            return
        if _is_repetition(expr):
            iterates = self.iteration_scope(expr)
            if id(expr) in self.ill_formed:
                return                      # its structure is the error; its reads would only repeat it
            body_scope = iterates if iterates is not None and len(iterates) > len(scope) else scope
        else:
            body_scope = scope
        if isinstance(expr, ShExJ.TripleConstraint):
            self.constraint(expr, body_scope)
        elif isinstance(expr, (ShExJ.EachOf, ShExJ.OneOf)):
            for e in expr.expressions:
                self.expression(e, body_scope)

    def constraint(self, tc, scope: Site) -> None:
        plain, keys = _variables(tc, self.prefixes)
        acts = map_actions(tc)
        if keys or any(functions.is_key_code(str(a.code or '')) for a in acts):
            if len(acts) > 1:
                self.report.error(f"id() must be the only Map code on {tc.predicate}")
            if not references_shape(tc.valueExpr):
                self.report.error(f"id() on {tc.predicate} needs a shape-valued constraint")
            if any(functions.NODE_ARGUMENT in functions.key_arguments(str(a.code or ''), self.prefixes)
                   for a in acts if functions.is_key_code(str(a.code or ''))) and not scope:
                self.report.error(f"id(@node) on {tc.predicate} is read at the root, where no input iteration "
                                  f"provides a node")
        for v in plain + keys:
            self.read_variable(v, tc, scope)
        if references_shape(tc.valueExpr):
            self.shape_expr(tc.valueExpr, scope)

    def read_variable(self, v: str, tc, scope: Site) -> None:
        self.report.read.add(v)
        if v in self.statics:
            return
        site = self.report.bound.get(v)
        if site is None:
            self.report.error(f"{tc.predicate} reads {v}, which the input schema never binds")
            return
        if scope[:len(site)] == site:
            return                          # bound here or above: readable
        if site[:len(scope)] == scope:
            self.report.error(
                f"{tc.predicate} reads {v}, bound once per {self.report.where(site)}, from "
                f"{self.report.where(scope)}: which one?  A repetition over it is needed")
        else:
            self.report.error(
                f"{tc.predicate} reads {v}, bound at {self.report.where(site)}, from "
                f"{self.report.where(scope)}, which is not below it")

    # -- iteration scopes ---------------------------------------------------------------
    def iteration_scope(self, expr) -> Site | None:
        key = id(expr)
        if key in self.scopes:
            return self.scopes[key]
        self.scopes[key] = None             # a recursive repetition counts as scope-free while computed
        direct: dict[str, object] = {}
        nested: list = []
        self.collect(expr, direct, nested, set(), top=True)
        candidates: dict[Site, str] = {}
        for v in direct:
            if v in self.report.bound:
                candidates.setdefault(self.report.bound[v], v)
        for r in nested:
            sub = self.iteration_scope(r)
            if sub:
                candidates.setdefault(sub[:-1], f"the repetition over {_label(r)}")
        result: Site | None = None
        if candidates:
            result = max(candidates, key=len)
            for site, why in candidates.items():
                if result[:len(site)] != site:
                    self.report.error(
                        f"the repetition over {_label(expr)} reads from unrelated lists: {why} is bound at "
                        f"{self.report.where(site)} and {candidates[result]} at {self.report.where(result)}")
                    self.ill_formed.add(key)
                    self.report.read.update(direct)
                    break
        self.scopes[key] = result
        return result

    def collect(self, expr, direct: dict, nested: list, seen: set, top: bool) -> None:
        if isinstance(expr, str):
            expr = self.cntxt.tripleExprFor(expr)
        if expr is None or id(expr) in seen:
            return
        seen.add(id(expr))
        if not top and _is_repetition(expr):
            nested.append(expr)
            return
        if isinstance(expr, ShExJ.TripleConstraint):
            plain, keys = _variables(expr, self.prefixes)
            for v in plain + keys:
                direct[v] = True
            if references_shape(expr.valueExpr):
                self.collect_shape(expr.valueExpr, direct, nested, seen)
        elif isinstance(expr, (ShExJ.EachOf, ShExJ.OneOf)):
            for e in expr.expressions:
                self.collect(e, direct, nested, seen, top=False)

    def collect_shape(self, se, direct: dict, nested: list, seen: set) -> None:
        if isinstance(se, str):
            decl = declaration_of(self.cntxt, se)
            if decl is None:
                return
            for o in extension_candidates(self.cntxt, decl):
                self.collect_shape(expression_of(o), direct, nested, seen)
            return
        if id(se) in seen:
            return
        seen.add(id(se))
        if isinstance(se, ShExJ.ShapeDecl):
            self.collect_shape(se.shapeExpr, direct, nested, seen)
        elif isinstance(se, ShExJ.Shape):
            for p in shape_parts(self.cntxt, se):
                if p.expression is not None:
                    self.collect(p.expression, direct, nested, seen, top=False)
        elif isinstance(se, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
            for p in se.shapeExprs:
                self.collect_shape(p, direct, nested, seen)
