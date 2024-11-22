
"""
Context for evaluation engine -- carries all of the global variables (schema, graph, etc.)

We might fold the various routines inside context and replace "cntxt: Context" with "self", but we will have to see.

"""
from collections import defaultdict
from copy import copy
from typing import Dict, Any, Callable, Optional, List, Tuple, Union, Set

from ShExJSG import ShExJ
from ShExJSG.ShExJ import Schema
from jsonasobj import JsonObj, as_dict
from pyjsg.jsglib import isinstance_
from rdflib import Graph, BNode, Namespace, URIRef, Literal

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Node
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import START
from pyshex.utils.n3_mapper import N3Mapper


class DebugContext:
    def __init__(self):
        self.debug = False
        self.trace_slurps = False
        self.trace_depth = 0
        self.held_prints: Dict[int, str] = defaultdict(str)
        self.max_print_depth: int = 0

    def d(self) -> str:
        """ Return a depth indicator """
        return f"({self.trace_depth})"

    def splus(self) -> None:
        self.trace_depth += 1

    def sminus(self) -> None:
        self.trace_depth -= 1

    @staticmethod
    def s(ndeep) -> str:
        return ' ' * (ndeep - 1)

    @staticmethod
    def rs(ndeep) -> str:
        return '\n' + DebugContext.s(ndeep)

    def i(self, bias: int, txt: str, txt_list: Optional[List[object]]=None) -> str:
        if txt_list is None:
            txt_list = []
        elif len(txt_list) > 1:
            txt_list.insert(0, '')
        return DebugContext.s(self.trace_depth + bias) + txt + ' ' + \
            DebugContext.rs(self.trace_depth + bias + 1).join(str(e) for e in txt_list)

    def print(self, txt: str, hold: bool=False) -> None:
        """ Conditionally print txt

        :param txt: text to print
        :param hold: If true, hang on to the text until another print comes through
        :param hold: If true, drop both print statements if another hasn't intervened
        :return:
        """
        if hold:
            self.held_prints[self.trace_depth] = txt
        elif self.held_prints[self.trace_depth]:
            if self.max_print_depth > self.trace_depth:
                print(self.held_prints[self.trace_depth])
                print(txt)
                self.max_print_depth = self.trace_depth
            del self.held_prints[self.trace_depth]
        else:
            print(txt)
            self.max_print_depth = self.trace_depth


class _VisitorCenter:
    """ A visitor context -- couldn't resist calling it Visitor Center, however... it is python, you know """
    def __init__(self, f: Callable[[Any, ShExJ.shapeExpr, "Context"], None], arg_cntxt: Any) \
            -> None:
        self.f = f
        self.arg_cntxt = arg_cntxt
        self._seen_shapes = []
        self._visiting_shapes = []
        self._seen_tes = []
        self._visiting_tes = []

    def start_visiting_shape(self, id_: str) -> None:
        self._visiting_shapes.append(id_)

    def actively_visiting_shape(self, id_: str) -> bool:
        return id_ in self._visiting_shapes

    def done_visiting_shape(self, id_: str) -> None:
        self._visiting_shapes.remove(id_)
        self._seen_shapes.append(id_)

    def already_seen_shape(self, id_: str) -> bool:
        return id_ in self._seen_shapes

    def start_visiting_te(self, id_: str) -> None:
        self._visiting_tes.append(id_)

    def actively_visiting_te(self, id_: str) -> bool:
        return id_ in self._visiting_tes

    def done_visiting_te(self, id_: str) -> None:
        self._visiting_tes.remove(id_)
        self._seen_tes.append(id_)

    def already_seen_te(self, id_: str) -> bool:
        return id_ in self._seen_tes


def default_external_shape_resolver(_: ShExJ.IRIREF) -> Optional[ShExJ.Shape]:
    """ Default external shape resolution function """
    return None


def default_shape_importer(_: ShExJ.IRIREF, cntxt: "Context") -> Optional[ShExJ.Schema]:
    """ Resolve an import declaration """
    return None


class Context:
    """ Environment for ShExJ evaluation """
    def __init__(self, g: Optional[Graph], s: Schema,
                 external_shape_resolver: Optional[Callable[[ShExJ.IRIREF], Optional[ShExJ.Shape]]]=None,
                 base_namespace: Optional[Namespace]=None,
                 shape_importer: Optional[Callable[[ShExJ.IRIREF], Optional[ShExJ.Schema]]]=None) -> None:
        """
        Create a context consisting of an RDF Graph and a ShEx Schema and generate a identifier to
        item map.

        :param g: RDF graph
        :param s: ShExJ Schema instance
        :param external_shape_resolver: External resolution function
        :param base_namespace:
        """
        self.is_valid: bool = True
        self.error_list: List[str] = []
        self.graph: Graph = g
        self.n3_mapper = N3Mapper(g)
        self.schema: ShExJ.Schema = s
        self.schema_id_map: Dict[ShExJ.shapeExprLabel, ShExJ.shapeExpr] = {}
        self.te_id_map: Dict[ShExJ.tripleExprLabel, ShExJ.tripleExpr] = {}
        self.external_shape_for = external_shape_resolver if external_shape_resolver \
            else default_external_shape_resolver
        self.base_namespace = base_namespace if isinstance(base_namespace, Namespace) \
            else Namespace(base_namespace) if base_namespace else None
        self.shape_importer = shape_importer if shape_importer else default_shape_importer

        # For SPARQL API's, true means pull ALL predicate objects for a given subject, false means only the
        # predicates that are needed
        self.over_slurp = True

        # A list of node selectors/shape expressions that are being evaluated.  If we attempt to evaluate
        # an entry for a second time, we, instead, put the entry into the assumptions table.  We start with 'true'
        # and, if the result is 'true' then we count it as success.  If not, we switch to false and try again
        self.evaluating: Set[Tuple[Node, ShExJ.shapeExprLabel]] = set()
        self.assumptions: Dict[Tuple[Node, ShExJ.shapeExprLabel], bool] = {}

        # Known results -- a cache of existing evaluation results
        self.known_results: Dict[Tuple[Node, ShExJ.shapeExprLabel], bool] = {}

        # Debugging options
        self.debug_context = DebugContext()

        # Process imports
        if self.schema.imports is not None:
            for uri in self.schema.imports:
                imp_shape = self.shape_importer(uri, self)
                if not imp_shape:
                    # TODO: what to do on import failure
                    self.is_valid = False
                    self.error_list.append(f"Import failure on {uri}")

        if self.schema.start is not None:
            if not isinstance_(self.schema.start, ShExJ.shapeExprLabel) and\
                    'id' in self.schema.start and self.schema.start.id is None:
                self.schema.start.id = "_:start"
            self._gen_schema_xref(self.schema.start)
            # TODO: The logic below really belongs in the parser.  We shouldn't be messing with the schema here...
            if not isinstance_(self.schema.start, ShExJ.shapeExprLabel):
                if self.schema.shapes is None:
                    self.schema.shapes = [self.schema.start]
                else:
                    self.schema.shapes.append(self.schema.start)
                self.schema.start = self.schema.start.id
        if self.schema.shapes is not None:
            for e in self.schema.shapes:
                self._gen_schema_xref(e)

        self.current_node: ParseNode = None
        self.evaluate_stack: List[Tuple[Union[BNode, URIRef], Optional[str]]] = []  # Node / shape evaluation stacks
        self.bnode_map: Dict[BNode, str] = {}       # Map for prettifying bnodes

    def reset(self) -> None:
        """
        Reset the context preceding an evaluation
        """
        self.evaluating = set()
        self.assumptions = {}
        self.known_results = {}
        self.current_node = None
        self.evaluate_stack = []
        self.bnode_map = {}

    def _gen_schema_xref(self, expr: Optional[Union[ShExJ.shapeExprLabel, ShExJ.shapeExpr]]) -> None:
        """
        Generate the schema_id_map

        :param expr: root shape expression
        """
        if expr is not None and not isinstance_(expr, ShExJ.shapeExprLabel) and 'id' in expr and expr.id is not None:
            abs_id = self._resolve_relative_uri(expr.id)
            if abs_id not in self.schema_id_map:
                self.schema_id_map[abs_id] = expr
        if isinstance(expr, (ShExJ.ShapeOr, ShExJ.ShapeAnd)):
            for expr2 in expr.shapeExprs:
                self._gen_schema_xref(expr2)
        elif isinstance(expr, ShExJ.ShapeNot):
            self._gen_schema_xref(expr.shapeExpr)
        elif isinstance(expr, ShExJ.Shape):
            if expr.expression is not None:
                self._gen_te_xref(expr.expression)

    def _resolve_relative_uri(self, ref: Union[URIRef, BNode, ShExJ.shapeExprLabel]) -> ShExJ.shapeExprLabel:
        return ShExJ.IRIREF(str(self.base_namespace[str(ref)])) if ':' not in str(ref) and self.base_namespace else ref

    def _gen_te_xref(self, expr: Union[ShExJ.tripleExpr, ShExJ.tripleExprLabel]) -> None:
        """
        Generate the triple expression map (te_id_map)

        :param expr: root triple expression

        """
        if expr is not None and not isinstance_(expr, ShExJ.tripleExprLabel) and 'id' in expr and expr.id is not None:
            if expr.id in self.te_id_map:
                return
            else:
                self.te_id_map[self._resolve_relative_uri(expr.id)] = expr
        if isinstance(expr, (ShExJ.OneOf, ShExJ.EachOf)):
            for expr2 in expr.expressions:
                self._gen_te_xref(expr2)
        elif isinstance(expr, ShExJ.TripleConstraint):
            if expr.valueExpr is not None:
                self._gen_schema_xref(expr.valueExpr)

    def tripleExprFor(self, id_: ShExJ.tripleExprLabel) -> ShExJ.tripleExpr:
        """ Return the triple expression that corresponds to id """
        return self.te_id_map.get(id_)

    def shapeExprFor(self, id_: Union[ShExJ.shapeExprLabel, START]) -> Optional[ShExJ.shapeExpr]:
        """ Return the shape expression that corresponds to id """
        rval = self.schema.start if id_ is START else self.schema_id_map.get(str(id_))
        return rval

    def visit_shapes(self, expr: ShExJ.shapeExpr, f: Callable[[Any, ShExJ.shapeExpr, "Context"], None], arg_cntxt: Any,
                     visit_center: _VisitorCenter = None, follow_inner_shapes: bool=True) -> None:
        """
        Visit expr and all of its "descendant" shapes.

        :param expr: root shape expression
        :param f: visitor function
        :param arg_cntxt: accompanying context for the visitor function
        :param visit_center: Recursive visit context.  (Not normally supplied on an external call)
        :param follow_inner_shapes: Follow nested shapes or just visit on outer level
        """
        if visit_center is None:
            visit_center = _VisitorCenter(f, arg_cntxt)
        has_id = getattr(expr, 'id', None) is not None
        if not has_id or not (visit_center.already_seen_shape(expr.id)
                              or visit_center.actively_visiting_shape(expr.id)):

            # Visit the root expression
            if has_id:
                visit_center.start_visiting_shape(expr.id)
            f(arg_cntxt, expr, self)

            # Traverse the expression and visit its components
            if isinstance(expr, (ShExJ.ShapeOr, ShExJ.ShapeAnd)):
                for expr2 in expr.shapeExprs:
                    self.visit_shapes(expr2, f, arg_cntxt, visit_center, follow_inner_shapes=follow_inner_shapes)
            elif isinstance(expr, ShExJ.ShapeNot):
                self.visit_shapes(expr.shapeExpr, f, arg_cntxt, visit_center, follow_inner_shapes=follow_inner_shapes)
            elif isinstance(expr, ShExJ.Shape):
                if expr.expression is not None and follow_inner_shapes:
                    self.visit_triple_expressions(expr.expression,
                                                  lambda ac, te, cntxt: self._visit_shape_te(te, visit_center),
                                                  arg_cntxt,
                                                  visit_center)
            elif isinstance_(expr, ShExJ.shapeExprLabel):
                if not visit_center.actively_visiting_shape(str(expr)) and follow_inner_shapes:
                    visit_center.start_visiting_shape(str(expr))
                    self.visit_shapes(self.shapeExprFor(expr), f, arg_cntxt, visit_center)
                    visit_center.done_visiting_shape(str(expr))
            if has_id:
                visit_center.done_visiting_shape(expr.id)

    def visit_triple_expressions(self, expr: ShExJ.tripleExpr, f: Callable[[Any, ShExJ.tripleExpr, "Context"], None],
                                 arg_cntxt: Any, visit_center: _VisitorCenter=None) -> None:
        if visit_center is None:
            visit_center = _VisitorCenter(f, arg_cntxt)
        if expr is None:
            return f(arg_cntxt, None, self)
        has_id = not isinstance_(expr, ShExJ.tripleExprLabel) and 'id' in expr and expr.id is not None
        if not has_id or not visit_center.already_seen_te(expr.id):

            # Visit the root expression
            if has_id:
                visit_center.start_visiting_te(expr.id)
            f(arg_cntxt, expr, self)

            # Visit all of the references
            if isinstance(expr, (ShExJ.EachOf, ShExJ.OneOf)):
                for expr2 in expr.expressions:
                    self.visit_triple_expressions(expr2, f, arg_cntxt, visit_center)
            elif isinstance(expr, ShExJ.TripleConstraint):
                if expr.valueExpr is not None:
                    self.visit_shapes(expr.valueExpr,
                                      lambda ac, te, cntxt: self._visit_shape_te(te, visit_center),
                                      arg_cntxt,
                                      visit_center)
            elif isinstance_(expr, ShExJ.tripleExprLabel):
                if not visit_center.actively_visiting_te(str(expr)):
                    visit_center.start_visiting_te(str(expr))
                    self.visit_triple_expressions(self.tripleExprFor(expr), f, arg_cntxt, visit_center)
                    visit_center.done_visiting_te(str(expr))
            if has_id:
                visit_center.done_visiting_te(expr.id)

    def _visit_shape_te(self, te: ShExJ.tripleExpr, visit_center: _VisitorCenter) -> None:
        """
        Visit a triple expression that was reached through a shape. This, in turn, is used to visit additional shapes
        that are referenced by a TripleConstraint
        :param te: Triple expression reached through a Shape.expression
        :param visit_center: context used in shape visitor
        """
        if isinstance(te, ShExJ.TripleConstraint) and te.valueExpr is not None:
            visit_center.f(visit_center.arg_cntxt, te.valueExpr, self)

    def _visit_te_shape(self, shape: ShExJ.shapeExpr, visit_center: _VisitorCenter) -> None:
        """
        Visit a shape expression that was reached through a triple expression.  This, in turn, is used to visit
        additional triple expressions that are referenced by the Shape

        :param shape: Shape reached through triple expression traverse
        :param visit_center: context used in shape visitor
        """
        if isinstance(shape, ShExJ.Shape) and shape.expression is not None:
            visit_center.f(visit_center.arg_cntxt, shape.expression, self)

    def start_evaluating(self, n: Node, s: ShExJ.shapeExpr) -> Optional[bool]:
        """Indicate that we are beginning to evaluate n according to shape expression s.
        If we are already in the process of evaluating (n,s), as indicated self.evaluating, we return our current
        guess as to the result.

        :param n: Node to be evaluated
        :param s: expression for node evaluation
        :return: Assumed evaluation result.  If None, evaluation must be performed
        """
        if not s.id:
            s.id = str(BNode())                 # Random permanent id
        key = (n, s.id)

        # We only evaluate a node once
        if key in self.known_results:
            return self.known_results[key]

        if key not in self.evaluating:
            self.evaluating.add(key)
            return None
        elif key not in self.assumptions:
            self.assumptions[key] = True
        return self.assumptions[key]

    def done_evaluating(self, n: Node, s: ShExJ.shapeExpr, result: bool) -> Tuple[bool, bool]:
        """
        Indicate that we have completed an actual evaluation of (n,s).  This is only called when start_evaluating
        has returned None as the assumed result

        :param n: Node that was evaluated
        :param s: expression for node evaluation
        :param result: result of evaluation
        :return: Tuple - first element is whether we are done, second is whether evaluation was consistent
        """
        key = (n, s.id)

        # If we didn't have to assume anything or our assumption was correct, we're done
        if key not in self.assumptions or self.assumptions[key] == result:
            if key in self.assumptions:
                del self.assumptions[key]       # good housekeeping, not strictly necessary
            self.evaluating.remove(key)
            self.known_results[key] = result
            return True, True
        # If we assumed true and got a false, try assuming false
        elif self.assumptions[key]:
            self.evaluating.remove(key)         # restart the evaluation from the top
            self.assumptions[key] = False
            return False, True
        else:
            self.fail_reason = f"{s.id}: Inconsistent recursive shape reference"
            return True, False

    def process_reasons(self) -> List[str]:
        return self.current_node.fail_reasons(self.graph)


    @property
    def fail_reason(self) -> str:
        return self.current_node._fail_reason

    @fail_reason.setter
    def fail_reason(self, reason_text: str) -> None:
        if self.current_node._fail_reason is None:
            self.current_node._fail_reason = reason_text
        else:
            self.current_node._fail_reason += '\n' + reason_text
        self.current_node.reason_stack = copy(self.evaluate_stack)

    def dump_bnode(self, n: Union[URIRef, BNode, Literal]) -> None:
        if isinstance(n, BNode):
            self.fail_reason = f"    {self.n3_mapper.n3(n)} context:"
            for entry in self.current_node.dump_bnodes(self.graph, n, '      '):
                self.fail_reason = entry

    def type_last(self, obj: JsonObj) -> JsonObj:
        """ Move the type identifiers to the end of the object for print purposes """
        def _tl_list(v: List) -> List:
            return [self.type_last(e) if isinstance(e, JsonObj)
                                   else _tl_list(e) if isinstance(e, list) else e for e in v if e is not None]

        rval = JsonObj()
        for k in as_dict(obj).keys():
            v = obj[k]
            if v is not None and k not in ('type', '_context'):
                rval[k] = _tl_list(v) if isinstance(v, list) else self.type_last(v) if isinstance(v, JsonObj) else v

        if 'type' in obj and obj.type:
            rval.type = obj.type
        return rval
