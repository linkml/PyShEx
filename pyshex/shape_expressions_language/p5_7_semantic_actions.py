"""
Implementation of `5.7 Semantic Actions <http://shex.io/shex-semantics/#semantic-actions>`_

A stub for the moment.
"""
from ShExJSG import ShExJ

from pyshex.shape_expressions_language.p5_context import Context


def semActsSatisfied(acts: list[ShExJ.SemAct] | None, cntxt: Context) -> bool:
    """ `5.7.1 Semantic Actions Semantics <http://shex.io/shex-semantics/#semantic-actions-semantics>`_

    The evaluation semActsSatisfied on a list of SemActs returns success or failure. The evaluation of an individual
    SemAct is implementation-dependent.
    """
    return True
