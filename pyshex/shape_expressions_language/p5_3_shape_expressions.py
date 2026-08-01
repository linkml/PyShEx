""" Implementation of `5.3 Shape Expressions <http://shex.io/shex-semantics/#node-constraint-semantics>`_ """

from ShExJSG import ShExJ
from pyjsg.jsglib import isinstance_

from pyshex.shape_expressions_language.p5_4_node_constraints import satisfiesNodeConstraint
from pyshex.shape_expressions_language.p5_5_shapes_and_triple_expressions import satisfiesShape, \
    _active_restriction, suspended_inherited_closed
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
            * Se is a ShapeExternal and implementation-specific mechansims not defined in this specification
            indicate success.
            * Se is a shapeExprRef and there exists in the schema a shape expression se2 with that id and
                      satisfies(n, se2, G, m).

          .. note:: Where is the documentation on recursion?  All I can find is
           `5.9.4 Recursion Example <http://shex.io/shex-semantics/#example-recursion>`_
          """
    if (isinstance(se, ShExJ.ShapeDecl) or getattr(se, 'abstract', None) or getattr(se, 'restricts', None)
        or (getattr(se, 'id', None) is not None and _extensions_index(cntxt).get(str(se.id)))) \
            and id(se) not in getattr(cntxt, '_decl_bypass', set()):
        # ShExJ 2.1 puts abstract/restricts on ShapeDecl; older parsers put them
        # directly on the shape expression.  Both flavours are handled here.
        rval = satisfiesShapeDecl(cntxt, n, se)
    elif isinstance(se, ShExJ.ShapeDecl):
        rval = satisfies(cntxt, n, se.shapeExpr)
    elif isinstance(se, ShExJ.NodeConstraint):
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


def satisfiesShapeDecl(cntxt: Context, n: Node, se) -> bool:
    """A ShapeDecl's restricts are additional conjuncts: the node must satisfy the
    declared shape expression and every restricted shape (cf. shex.js validateShapeDecl,
    which conjoins restricts + shapeExpr as a ShapeAnd).  An abstract declaration cannot
    be satisfied directly: some non-abstract declaration extending it must be satisfied
    instead -- except when the declaration is being evaluated as an EXTENDS target
    against its allocated part of the neighbourhood, where the extension mechanism has
    already chosen it (cf. shex.js validateDescendants under a subGraph)."""

    inner = se.shapeExpr if isinstance(se, ShExJ.ShapeDecl) else se

    def direct() -> bool:
        # ShExJ 2.1 moved labels onto ShapeDecl: a ShapeExternal no longer carries the
        # id that external resolution is keyed on, so pass the declaration's down.
        if isinstance(inner, ShExJ.ShapeExternal) and getattr(inner, 'id', None) is None:
            inner.id = se.id
        if inner is se:
            # legacy flavour: the abstract/restricts live on the expression itself;
            # bypass the declaration branch when recursing into it
            if not hasattr(cntxt, '_decl_bypass'):
                cntxt._decl_bypass = set()
            cntxt._decl_bypass.add(id(se))
            try:
                rslt = satisfies(cntxt, n, inner)
            finally:
                cntxt._decl_bypass.discard(id(se))
        else:
            rslt = satisfies(cntxt, n, inner)
        return rslt and all(satisfies(cntxt, n, r) for r in (getattr(se, 'restricts', None) or []))

    if _active_restriction(cntxt, n) is not None:
        return direct()
    if (not getattr(se, 'abstract', None)) and direct():
        return True
    return any(satisfiesShapeDecl(cntxt, n, d) for d in _non_abstract_descendants(cntxt, se))


def _extensions_index(cntxt: Context) -> dict[str, list]:
    """parent shape label -> declarations that extend it (directly), computed once."""
    if not hasattr(cntxt, '_extensions_children'):
        children: dict[str, list] = {}
        for decl in cntxt.schema.shapes or []:
            if not isinstance(decl, ShExJ.ShapeDecl) and getattr(decl, 'id', None) is None:
                continue
            parents: set[str] = set()

            def walk(e) -> None:
                if e is None or isinstance_(e, ShExJ.shapeExprLabel):
                    return
                if isinstance(e, (ShExJ.ShapeAnd, ShExJ.ShapeOr)):
                    for nested in e.shapeExprs:
                        walk(nested)
                elif isinstance(e, ShExJ.ShapeNot):
                    walk(e.shapeExpr)
                elif isinstance(e, ShExJ.Shape):
                    for parent in getattr(e, 'extends', None) or []:
                        parents.add(str(parent))

            walk(decl.shapeExpr if isinstance(decl, ShExJ.ShapeDecl) else decl)
            for parent in parents:
                children.setdefault(parent, []).append(decl)
        cntxt._extensions_children = children
    return cntxt._extensions_children


def _non_abstract_descendants(cntxt: Context, decl: ShExJ.ShapeDecl) -> list:
    """The non-abstract declarations that transitively extend decl."""
    index = _extensions_index(cntxt)
    result: list = []
    seen: set[str] = {str(decl.id)}
    stack: list[str] = [str(decl.id)]
    while stack:
        for child in index.get(stack.pop(), []):
            child_id = str(child.id)
            if child_id in seen:
                continue
            seen.add(child_id)
            stack.append(child_id)
            if not getattr(child, 'abstract', None):
                result.append(child)
    return result


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
    with suspended_inherited_closed(cntxt, n):
        return all(satisfies(cntxt, n, se2) for se2 in se.shapeExprs)


@trace_satisfies()
def satisfiesShapeNot(cntxt: Context, n: Node, se: ShExJ.ShapeNot, _: DebugContext) -> bool:
    """ Se is a ShapeNot and for the shape expression se2 at shapeExpr, notSatisfies(n, se2, G, m) """
    with suspended_inherited_closed(cntxt, n):
        return not satisfies(cntxt, n, se.shapeExpr)


@trace_satisfies(True)
def satisfiesExternal(cntxt: Context, n: Node, se: ShExJ.ShapeExternal, c: DebugContext) -> bool:
    """ Se is a ShapeExternal and implementation-specific mechansims not defined in this specification indicate
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
