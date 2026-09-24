"""
Implementation of `5.7 Semantic Actions <http://shex.io/shex-semantics/#semantic-actions>`_

The evaluation of an individual SemAct is implementation-dependent.  Extensions are looked
up by their IRI in a registry (see :func:`register_extension`); actions of unregistered
extensions succeed silently.  Built in is the `Test extension <http://shex.io/extensions/Test/>`_
used by the shexTest suite: ``print(arg)`` succeeds and ``fail(arg)`` fails, each recording its
argument -- a double-quoted string literal or one of s/p/o naming a component of the
triples being matched -- on ``cntxt.semact_prints``.
"""
import re
from collections.abc import Callable

from ShExJSG import ShExJ

from pyshex.shape_expressions_language.p5_context import Context

TEST_EXTENSION = "http://shex.io/extensions/Test/"

_TEST_CODE = re.compile(r'\s*(?P<op>print|fail)\s*\(\s*(?:"(?P<string>(?:[^"\\]|\\.)*)"|(?P<term>[spo]))\s*\)\s*$')


def semActsSatisfied(acts: list[ShExJ.SemAct] | None, cntxt: Context, T=None) -> bool:
    """ `5.7.1 Semantic Actions Semantics <http://shex.io/shex-semantics/#semantic-actions-semantics>`_

    The evaluation semActsSatisfied on a list of SemActs returns success or failure.  A
    failing action aborts the list: actions after it are not evaluated.

    :param acts: semantic actions to evaluate
    :param cntxt: evaluation context
    :param T: the triples being matched, when the actions accompany a triple expression
    """
    return all(_semActSatisfied(act, cntxt, T) for act in acts or [])


SemActHandler = Callable[[ShExJ.SemAct, Context, object], bool]
"""An extension handler: given the action, the evaluation context and the triples being
matched (None for start actions), return whether the action succeeds.  A handler that
fails may set ``cntxt.fail_reason``."""

_EXTENSIONS: dict[str, SemActHandler] = {}


def register_extension(iri: str, handler: SemActHandler) -> None:
    """Evaluate semantic actions named ``iri`` with ``handler``.  Registering the same
    IRI again replaces the previous handler."""
    _EXTENSIONS[str(iri)] = handler


def unregister_extension(iri: str) -> None:
    """Stop evaluating semantic actions named ``iri``; they succeed silently again."""
    _EXTENSIONS.pop(str(iri), None)


def _semActSatisfied(act: ShExJ.SemAct, cntxt: Context, T) -> bool:
    handler = _EXTENSIONS.get(str(act.name))
    return True if handler is None else handler(act, cntxt, T)


def _test_extension(act: ShExJ.SemAct, cntxt: Context, T) -> bool:
    parsed = _TEST_CODE.match(str(act.code)) if act.code is not None else None
    if parsed is None:
        return True
    if parsed.group('string') is not None:
        printed = [re.sub(r'\\(.)', r'\1', parsed.group('string'))]
    else:
        component = {'s': 0, 'p': 1, 'o': 2}[parsed.group('term')]
        printed = [str(t[component]) for t in sorted(T)] if T is not None else []
    recorded_prints(cntxt).extend(printed)
    if parsed.group('op') == 'fail':
        # startActs run before any node evaluation begins, where there is no current
        # parse node to attach a failure reason to
        if getattr(cntxt, 'current_node', None) is not None:
            cntxt.fail_reason = f"Semantic action failed: {str(act.code).strip()}"
        return False
    return True


def recorded_prints(cntxt: Context) -> list[str]:
    """The strings Test-extension actions have printed during this evaluation."""
    if not hasattr(cntxt, 'semact_prints'):
        cntxt.semact_prints = []
    return cntxt.semact_prints


register_extension(TEST_EXTENSION, _test_extension)
