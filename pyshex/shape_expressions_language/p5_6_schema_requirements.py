""" Implementation of `5.6 Schema Requirements <http://shex.io/shex-semantics/#schema-requirements>`_

The semantics defined above assume two structural requirements beyond those imposed by the grammar of the
abstract syntax. These ensure referential integrity and eliminate logical paradoxes such as those that arrise
through the use of negation. These are not constraints expressed by the schema but instead those imposed on
the schema.
"""
from ShExJSG import ShExJ

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Node


def conforms(cntxt: Context, n: Node, S: ShExJ.Shape) -> bool:
    """ `5.6.1 Schema Validation Requirement <http://shex.io/shex-semantics/#validation-requirement>`_
    
    A graph G is said to conform with a schema S with a ShapeMap m when:

    Every, SemAct in the startActs of S has a successful evaluation of semActsSatisfied.
    Every node n in m conforms to its associated shapeExprRefs sen where for each shapeExprRef sei in sen:
        sei references a ShapeExpr in shapes, and
        satisfies(n, sei, G, m) for each shape sei in sen.

    :return:
    """
    # return semActsSatisfied(cntxt.schema.startActs, cntxt) and \
    #     all(reference_of(cntxt.schema, sa.shapeLabel) is not None and
    #
    return True


def valid_shape_references(S: ShExJ.Schema, cntxt: Context) -> bool:
    """ `5.6.2 Shape Expression Reference Requirement <http://shex.io/shex-semantics/#shapeExprRef-requirement>`_"""
    return True


def valid_triple_references(S: ShExJ.Schema, cntxt: Context) -> bool:
    """ `5.6.3 Triple Expression Reference Requirement <http://shex.io/shex-semantics/#tripleExprRef-requirement>`_"""
    return True


def valid_negations(S: ShExJ.Schema, cntxt: Context) -> bool:
    """ `5.6.4 <http://shex.io/shex-semantics/#negation-requirement>`_"""
    return True
