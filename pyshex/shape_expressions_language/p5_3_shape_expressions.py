""" Implementation of `5.3 Shape Expressions <http://shex.io/shex-semantics/#node-constraint-semantics>`_ """

from ShExJSG import ShExJ
from pyjsg.jsglib import isinstance_

from pyshex.shape_expressions_language.p5_4_node_constraints import satisfiesNodeConstraint
from pyshex.shape_expressions_language.p5_5_shapes_and_triple_expressions import satisfiesShape
from pyshex.shape_expressions_language.p5_context import Context, DebugContext
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Node
from pyshex.utils.trace_utils import trace_satisfies


def satisfies(cntxt: Context, n: Node, se: ShExJ.shapeExpr) -> bool:
    """ `5.3 Shape Expressions <http://shex.io/shex-semantics/#node-constraint-semantics>`_

          satisfies: The expression satisfies(n, se, G, m) indicates that a node n and graph G satisfy a shape
                      expression se with shapeMap m.

           satisfies(n, se, G, m) is true if and only if:

            * Se is a NodeConstraint and satisfies2(n, se) as described below in Node Constraints.
                      Note that testing if a node satisfies a node constraint does not require a graph or shapeMap.
            * Se is a Shape and satisfies(n, se) as defined below in Shapes and Triple Expressions.
            * Se is a ShapeOr and there is some shape expression se2 in shapeExprs such that
            satisfies(n, se2, G, m).
            * Se is a ShapeAnd and for every shape expression se2 in shapeExprs, satisfies(n, se2, G, m).
            * Se is a ShapeNot and for the shape expression se2 at shapeExpr, notSatisfies(n, se2, G, m).
            * Se is a ShapeExternal and implementation-specific mechanisms not defined in this specification
            indicate success.
            * Se is a shapeExprRef and there exists in the schema a shape expression se2 with that id and
                      satisfies(n, se2, G, m).

          .. note:: Where is the documentation on recursion?  All I can find is
           `5.9.4 Recursion Example <http://shex.io/shex-semantics/#example-recursion>`_
          """
    if isinstance(se, ShExJ.NodeConstraint):
        rval = satisfiesNodeConstraint(cntxt, n, se)
    elif isinstance(se, ShExJ.Shape):
        rval = satisfiesShape(cntxt, n, se)
    elif isinstance(se, ShExJ.ShapeOr):
        rval = satisifesShapeOr(cntxt, n, se)
    elif isinstance(se, ShExJ.ShapeAnd):
        rval = satisfiesShapeAnd(cntxt, n, se)
    elif isinstance(se, ShExJ.ShapeNot):
        rval = satisfiesShapeNot(cntxt, n, se)
    elif isinstance(se, ShExJ.ShapeExternal):
        rval = satisfiesExternal(cntxt, n, se)
    elif isinstance_(se, ShExJ.shapeExprLabel):
        rval = satisfiesShapeExprRef(cntxt, n, se)
    else:
        raise NotImplementedError(f"Unrecognized shapeExpr: {type(se)}")
    return rval


@trace_satisfies()
def notSatisfies(cntxt: Context, n: Node, se: ShExJ.shapeExpr, _: DebugContext) -> bool:
    return not satisfies(cntxt, n, se)


@trace_satisfies()
def satisifesShapeOr(cntxt: Context, n: Node, se: ShExJ.ShapeOr, _: DebugContext) -> bool:
    """ Se is a ShapeOr and there is some shape expression se2 in shapeExprs such that satisfies(n, se2, G, m). """
    return any(satisfies(cntxt, n, se2) for se2 in se.shapeExprs)


@trace_satisfies()
def satisfiesShapeAnd(cntxt: Context, n: Node, se: ShExJ.ShapeAnd, _: DebugContext) -> bool:
    """ Se is a ShapeAnd and for every shape expression se2 in shapeExprs, satisfies(n, se2, G, m) """
    return all(satisfies(cntxt, n, se2) for se2 in se.shapeExprs)


@trace_satisfies()
def satisfiesShapeNot(cntxt: Context, n: Node, se: ShExJ.ShapeNot, _: DebugContext) -> bool:
    """ Se is a ShapeNot and for the shape expression se2 at shapeExpr, notSatisfies(n, se2, G, m) """
    return not satisfies(cntxt, n, se.shapeExpr)


@trace_satisfies(True)
def satisfiesExternal(cntxt: Context, n: Node, se: ShExJ.ShapeExternal, c: DebugContext) -> bool:
    """ Se is a ShapeExternal and implementation-specific mechanisms not defined in this specification indicate
     success.
     """
    if c.debug:
        print(f"id: {se.id}")
    extern_shape = cntxt.external_shape_for(se.id)
    if extern_shape:
        return satisfies(cntxt, n, extern_shape)
    cntxt.fail_reason = f"{se.id}: Shape is not in Schema"
    return False


@trace_satisfies(True)
def satisfiesShapeExprRef(cntxt: Context, n: Node, se: ShExJ.shapeExprLabel, c: DebugContext) -> bool:
    """ Se is a shapeExprRef and there exists in the schema a shape expression se2 with that id
     and satisfies(n, se2, G, m).
     """
    if c.debug:
        print(f"id: {se}")
    for shape in cntxt.schema.shapes:
        if shape.id == se:
            return satisfies(cntxt, n, shape)
    cntxt.fail_reason = f"{se}: Shape is not in Schema"
    return False
