from ShExJSG import ShExJ
from ShExJSG.ShExJ import IRIREF

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START, shapeLabel


def reference_of(selector: shapeLabel, cntxt: Context | ShExJ.Schema ) -> ShExJ.shapeExpr | None:
    """ Return the shape expression in the schema referenced by selector, if any

    :param cntxt: Context node or ShEx Schema
    :param selector: identifier of element to select within the schema
    :return:
    """
    schema = cntxt.schema if isinstance(cntxt, Context) else cntxt
    if selector is START:
        return schema.start
    for expr in schema.shapes:
        if not isinstance(expr, ShExJ.ShapeExternal) and expr.id == selector:
            return expr
    return schema.start if schema.start is not None and schema.start.id == selector else None


def triple_reference_of(label: ShExJ.tripleExprLabel, cntxt: Context) -> ShExJ.tripleExpr | None:
    """ Search for the label in a Schema """
    te: ShExJ.tripleExpr | None = None
    if cntxt.schema.start is not None:
        te = triple_in_shape(cntxt.schema.start, label, cntxt)
    if te is None:
        for shapeExpr in cntxt.schema.shapes:
            te = triple_in_shape(shapeExpr, label, cntxt)
            if te:
                break
    return te


def triple_in_shape(expr: ShExJ.shapeExpr, label: ShExJ.tripleExprLabel, cntxt: Context) \
        -> ShExJ.tripleExpr | None:
    """ Search for the label in a shape expression """
    te = None
    if isinstance(expr, (ShExJ.ShapeOr, ShExJ.ShapeAnd)):
        for expr2 in expr.shapeExprs:
            te = triple_in_shape(expr2, label, cntxt)
            if te is not None:
                break
    elif isinstance(expr, ShExJ.ShapeNot):
        te = triple_in_shape(expr.shapeExpr, label, cntxt)
    elif isinstance(expr, ShExJ.shapeExprLabel):
        se = reference_of(expr, cntxt)
        if se is not None:
            te = triple_in_shape(se, label, cntxt)
    return te


def triple_constraints_in_expression(expression: ShExJ.shapeExpr, cntxt: Context) -> list[ShExJ.TripleConstraint]:
    tes: list[ShExJ.TripleConstraint] = []

    def triple_expr_visitor(tes: list[ShExJ.TripleConstraint], expr: ShExJ.TripleConstraint, _: Context) -> None:
        if isinstance(expr, ShExJ.TripleConstraint):
            tes.append(expr)

    cntxt.visit_triple_expressions(expression, triple_expr_visitor, tes)
    return tes


def predicates_in_expression(expression: ShExJ.shapeExpr, cntxt: Context) -> list[IRIREF]:
    """ Return the set of predicates that "appears in a TripleConstraint in an expression
    
    See: `5.5.2 Semantics <http://shex.io/shex-semantics/#triple-expressions-semantics>`_ for details

    :param expression: Expression to scan for predicates
    :param cntxt: Context of evaluation
    :return: list of predicates
    """
    return list(directed_predicates_in_expression(expression, cntxt).keys())


class PredDirection:
    def __init__(self) -> None:
        self.is_fwd = False
        self.is_rev = False

    def dir(self, is_fwd: bool) -> None:
        if is_fwd:
            self.is_fwd = True
        else:
            self.is_rev = True


def directed_predicates_in_expression(expression: ShExJ.shapeExpr, cntxt: Context) -> dict[IRIREF, PredDirection]:
    """ Directed predicates in expression -- return all predicates in shapeExpr along with which direction(s) they
    evaluate

    :param expression: Expression to scan
    :param cntxt:
    :return:
    """
    dir_predicates: dict[IRIREF, PredDirection] = {}

    def predicate_finder(predicates: dict[IRIREF, PredDirection], tc: ShExJ.TripleConstraint, _: Context) -> None:
        if isinstance(tc, ShExJ.TripleConstraint):
            predicates.setdefault(tc.predicate, PredDirection()).dir(tc.inverse is None or not tc.inverse)

    def triple_expr_finder(predicates: dict[IRIREF, PredDirection], expr: ShExJ.shapeExpr, cntxt_: Context) -> None:
        if isinstance(expr, ShExJ.Shape) and expr.expression is not None:
            cntxt_.visit_triple_expressions(expr.expression, predicate_finder, predicates)

    # TODO: follow_inner_shapes as True probably goes too far, but we definitely need to cross shape/triplecons
    cntxt.visit_shapes(expression, triple_expr_finder, dir_predicates, follow_inner_shapes=False)
    return dir_predicates


def predicates_in_tripleexpr(expression: ShExJ.tripleExpr, cntxt: Context) -> set[IRIREF]:
    predicates: set[IRIREF] = set()

    def triple_expr_visitor(predicates: set[IRIREF], expr: ShExJ.tripleExpr, cntxt_: Context) -> None:
        if isinstance(expr, ShExJ.TripleConstraint):
            predicates.add(expr.predicate)

    cntxt.visit_triple_expressions(expression, triple_expr_visitor, predicates)
    return predicates
