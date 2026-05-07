""" Implementation of `5.2 Validation Definition <http://shex.io/shex-semantics/#validation>`_ """
from pyjsg.jsglib import isinstance_

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_3_shape_expressions import satisfies
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Node
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import FixedShapeMap, START, nodeSelector


def isValid(cntxt: Context, m: FixedShapeMap) -> tuple[bool, list[str]]:
    """`5.2 Validation Definition <http://shex.io/shex-semantics/#validation>`_

    The expression isValid(G, m) indicates that for every nodeSelector/shapeLabel pair (n, s) in m, s has a
        corresponding shape expression se and satisfies(n, se, G, m). satisfies is defined below for each form
        of shape expression

    :param cntxt: evaluation context - includes graph and schema
    :param m: list of NodeShape pairs to test
    :return: Success/failure indicator and, if fail, a list of failure reasons
    """
    if not cntxt.is_valid:
        return False, cntxt.error_list
    parse_nodes = []
    for nodeshapepair in m:
        n = nodeshapepair.nodeSelector
        if not isinstance_(n, Node):
            return False, [f"{n}: Triple patterns are not implemented"]
        # The third test below is because the spec asserts that completely empty graphs pass in certain circumstances
        elif not (next(cntxt.graph.predicate_objects(nodeshapepair.nodeSelector), None) or
                  next(cntxt.graph.subject_predicates(nodeshapepair.nodeSelector), None) or
                  not next(cntxt.graph.triples((None, None, None)), None)):
            return False, [f"Focus: {nodeshapepair.nodeSelector} not in graph"]
        else:
            s = cntxt.shapeExprFor(START if nodeshapepair.shapeLabel is None or nodeshapepair.shapeLabel is START
                                   else nodeshapepair.shapeLabel)
            cntxt.current_node = ParseNode(satisfies, s, n, cntxt)
            if not s:
                if nodeshapepair.shapeLabel is START or nodeshapepair.shapeLabel is None:
                    cntxt.fail_reason = "START node is not specified or is invalid"
                else:
                    cntxt.fail_reason = f"Shape: {nodeshapepair.shapeLabel} not found in Schema"
                return False, cntxt.process_reasons()
            parse_nodes.append(cntxt.current_node)
            if not satisfies(cntxt, n, s):
                cntxt.current_node.result = False
                return False, cntxt.process_reasons()
            else:
                cntxt.current_node.result = True
    return True, []
