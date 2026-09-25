"""Validation-time handling of ``%Map:{ ... %}`` semantic actions.

Binding a plain variable cannot fail.  A function call, such as ``regex(...)`` that
does not match, fails the triple constraint it annotates, as in shex.js.  Bindings are
collected after validation by :func:`pyshex.shexmap.bind`.
"""
from ShExJSG import ShExJ

from pyshex.shape_expressions_language.p5_7_semantic_actions import register_extension
from pyshex.shexmap import functions
from pyshex.shexmap.bindings import MAP_EXTENSION, triple_constraints


def _owning_constraint(act: ShExJ.SemAct, cntxt) -> ShExJ.TripleConstraint | None:
    """The triple constraint an action annotates (to know whether it is inverse)."""
    index = getattr(cntxt, '_shexmap_act_owner', None)
    if index is None:
        index = {}
        for shape in cntxt.schema.shapes or []:
            for tc in triple_constraints(shape, cntxt):
                for a in getattr(tc, 'semActs', None) or []:
                    index[id(a)] = tc
        cntxt._shexmap_act_owner = index
    return index.get(id(act))


def map_action_satisfied(act: ShExJ.SemAct, cntxt, T) -> bool:
    code = str(act.code or '')
    if T is None or not functions.is_function_call(code):
        return True
    tc = _owning_constraint(act, cntxt)
    inverse = bool(tc is not None and tc.inverse)
    prefixes = getattr(cntxt, 'shexmap_prefixes', None)
    for t in T:
        try:
            functions.lift(code, t[0] if inverse else t[2], prefixes or _AnyPrefix())
        except functions.MapFunctionError as e:
            if getattr(cntxt, 'current_node', None) is not None:
                cntxt.fail_reason = f"ShExMap: {e}"
            return False
    return True


class _AnyPrefix(dict):
    """Prefixes are not known during validation; any prefix expands to a placeholder."""
    def __contains__(self, key) -> bool:
        return True

    def __getitem__(self, key) -> str:
        return f"urn:shexmap-prefix:{key}:"


def register() -> None:
    """Handle ``%Map:{ %}`` actions during validation.  Idempotent."""
    register_extension(MAP_EXTENSION, map_action_satisfied)
