from typing import Dict, List, Tuple, Set

from ShExJSG import ShExJ
from ShExJSG.ShExJ import IRIREF

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph
from pyshex.utils.partitions import partition_t
from pyshex.utils.schema_utils import predicates_in_tripleexpr


class EachOfEvaluator:
    def __init__(self, cntxt: Context, T: RDFGraph, expr: ShExJ.EachOf) -> None:
        """ Create an evaluator for expr and T

        :param cntxt: evaluation context
        :param T: List of triples to evaluate
        :param expr: expression to evaluate against
        """
        # tripleExpr = Union["EachOf", "OneOf", "TripleConstraint", tripleExprLabel]
        #
        # For each tripleExpr in expressions determine the set of applicable predicates and their
        # corresponding triples.
        #
        #       Case 1: predicate occurs in exactly one expression and expression references exactly one predicate
        #                   Evaluate and return false if fail
        #       Case 2: predicate occurs two or more expressions and all expressions reference exactly one predicate
        #                   Permute predicate over expressions until a passing condition is found
        #       Case 3: expression references two or more predicates and all referenced predicates occur only once
        #                   Evaluate with set of all predicates and return false if fail
        #       Case 4: predicate occurs in two or more expressions and at least one of the referenced expressions
        self.expressions: List[ShExJ.tripleExpr] = []

        self.predicate_to_expression_nums: Dict[IRIREF, List[int]] = {}
        self.expression_num_predicates: List[Set[IRIREF]] = []
        self.predicate_graph: Dict[IRIREF, RDFGraph] = {}

        for e in expr.expressions:
            expr_num = len(self.expressions)
            self.expressions.append(e)
            self.expression_num_predicates.append(predicates_in_tripleexpr(e, cntxt))
            for p in self.expression_num_predicates[expr_num]:
                self.predicate_to_expression_nums.setdefault(p, []).append(expr_num)
                if p not in self.predicate_graph:
                    self.predicate_graph[p] = RDFGraph([t for t in T if str(t.p) == str(p)])

    def evaluate(self, cntxt: Context) -> bool:
        from pyshex.shape_expressions_language.p5_5_shapes_and_triple_expressions import matches

        for p, expr_nums in self.predicate_to_expression_nums.items():
            if all(len(self.expression_num_predicates[expr_num]) == 1 for expr_num in expr_nums):
                if len(expr_nums) == 1:
                    # Case 1: unique predicate/expression combo
                    if not matches(cntxt, self.predicate_graph[p], self.expressions[expr_nums[0]]):
                        return False
                else:
                    # Case 2: several expressions match exactly one predicate -- split the triples
                    successful_combination = False
                    for partition in partition_t(self.predicate_graph[p], len(expr_nums)):
                        if all(matches(cntxt, t, self.expressions[e_num]) for t, e_num in zip(partition, expr_nums)):
                            successful_combination = True
                            break
                    if not successful_combination:
                        return False

        for expr_num in range(0, len(self.expression_num_predicates)):
            predicates = self.expression_num_predicates[expr_num]
            if len(predicates) > 1:

                # Case 3: Expression matches multiple predicates but each predicate referenced only once
                # Build a composite graph of all triples and evaluate it
                target = RDFGraph()
                for p in predicates:
                    if len(self.predicate_to_expression_nums[p]) == 1:
                        target.update(self.predicate_graph[p])
                if target and not matches(cntxt, target, self.expressions[expr_num]):
                    return False

                for p in predicates:
                    if len(self.predicate_to_expression_nums[p]) > 1:
                        predicates, expressions = self._predicate_closure(p)
                        target = RDFGraph()
                        for predicate in predicates:
                            target.update(self.predicate_graph[predicate])
                        successful_combination = True
                        for partition in partition_t(target, len(expressions)):
                            if all(matches(cntxt, t, self.expressions[e_num])
                                   for t, e_num in zip(partition, expressions)):
                                successful_combination = True
                                break
                        if not successful_combination:
                            return False
        return True

    def _predicate_closure(self,
                           predicate: IRIREF,
                           referenced_predicates: List[IRIREF] = None,
                           referenced_expressions: List[int] = None) \
            -> Tuple[List[IRIREF], List[int]]:
        if referenced_predicates is None:
            referenced_predicates = []
        if referenced_expressions is None:
            referenced_expressions = []
        referenced_predicates.append(predicate)
        for expression_num in self.predicate_to_expression_nums[predicate]:
            if expression_num not in referenced_expressions:
                referenced_expressions.append(expression_num)
                for expression_predicate in self.expression_num_predicates[expression_num]:
                    self._predicate_closure(expression_predicate,
                                            referenced_predicates,
                                            referenced_expressions)
        return referenced_predicates, referenced_expressions
