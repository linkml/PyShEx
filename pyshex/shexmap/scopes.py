"""The scope tree: a binding tree read structurally, for materialization by iteration scopes.

A binding tree (see :mod:`pyshex.shexmap.bindings`) is a *scope*: an object of own
bindings, or an array whose first element is that object and whose other elements are
*lists*, each list holding one *iteration* (a scope) per match of a repeated constraint or
group.  :func:`parse_scope` builds :class:`Scope` objects from a tree, accepting the two
older layouts shex.js and PyShEx wrote (``L1``, ``L2`` in the design notes), and
:class:`ScopeTree` answers the questions materialization asks: at what list a variable is
bound, and which scopes under a given one belong to a given list.

A **list path** names a list by position: the tuple of list indices from the root, so
``()`` is the root scope itself, ``(0,)`` the root's first list, ``(0, 1)`` the second list
of an iteration of that list.  Every iteration of a list shares the list's path; a variable
bound in those iterations is *bound at* that list path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rdflib.term import Node

from pyshex.shexmap.bindings import NODE_KEY

ListPath = tuple[int, ...]


class BindingTreeError(ValueError):
    """The binding tree is not a scope tree (nor one of the older layouts)."""


@dataclass
class Scope:
    own: dict[str, Node]                        # variables bound here (never @node)
    node: Node | None = None                    # the node this iteration matched, if recorded
    lists: list[list[Scope]] = field(default_factory=list)
    parent: Scope | None = None
    list_path: ListPath = ()                    # the list this scope is an iteration of
    path: tuple[int, ...] = ()                  # (list index, iteration index, ...) from the root

    @property
    def depth(self) -> int:
        return len(self.list_path)

    def lookup(self, var: str):
        """(value, scope) for ``var`` from here or the nearest ancestor binding it, else None."""
        s: Scope | None = self
        while s is not None:
            if var in s.own:
                return s.own[var], s
            s = s.parent
        return None

    def nearest_node(self) -> Node | None:
        """The node of this scope or of the nearest ancestor that recorded one."""
        s: Scope | None = self
        while s is not None:
            if s.node is not None:
                return s.node
            s = s.parent
        return None

    def descendants_at(self, list_path: ListPath) -> list[Scope]:
        """The scopes below this one that are iterations of ``list_path``, in document order."""
        if not _prefix(self.list_path, list_path) or list_path == self.list_path:
            return []
        out: list[Scope] = []
        for lst in self.lists:
            for it in lst:
                if it.list_path == list_path:
                    out.append(it)
                elif _prefix(it.list_path, list_path):
                    out.extend(it.descendants_at(list_path))
        return out

    def walk(self):
        yield self
        for lst in self.lists:
            for it in lst:
                yield from it.walk()


def _prefix(a: tuple, b: tuple) -> bool:
    return b[:len(a)] == a


def _is_scope_array(a) -> bool:
    return isinstance(a, list) and len(a) >= 1 and isinstance(a[0], dict) and all(isinstance(e, list) for e in a[1:])


def parse_scope(tree) -> Scope:
    """The scope tree of a binding tree (rdflib terms or JSON terms as values are both fine)."""
    if isinstance(tree, dict) or _is_scope_array(tree):
        return _scope(tree, None, (), ())
    if isinstance(tree, list):
        # L1: a root without own bindings, written without its object
        if all(isinstance(e, dict) for e in tree):                    # shex.js: the root's one list
            return _scope([{}, tree], None, (), ())
        if all(isinstance(e, list) for e in tree):
            if all(_is_scope_array(e) for e in tree):                   # shex.js: one list of scope iterations
                return _scope([{}, tree], None, (), ())
            if all(all(isinstance(x, dict) for x in e) for e in tree):  # PyShEx before 2026-09-27: the lists
                return _scope([{}, *tree], None, (), ())
    raise BindingTreeError(f"not a scope: {_short(tree)}")


def _scope(node, parent: Scope | None, list_path: ListPath, path: tuple[int, ...]) -> Scope:
    own = node if isinstance(node, dict) else node[0]
    lists = [] if isinstance(node, dict) else node[1:]
    scope = Scope({k: v for k, v in own.items() if not k.startswith("@")}, own.get(NODE_KEY), [], parent, list_path, path)
    for i, lst in enumerate(lists):
        if not isinstance(lst, list):
            raise BindingTreeError(f"a scope's lists must be arrays: {_short(lst)}")
        scope.lists.append([_iteration(e, scope, list_path + (i,), path + (i, j)) for j, e in enumerate(lst)])
    return scope


def _iteration(elt, parent: Scope, list_path: ListPath, path: tuple[int, ...]) -> Scope:
    if isinstance(elt, dict):
        return _scope(elt, parent, list_path, path)
    if _is_scope_array(elt):        # a scope array; also L2 (shex.js writes a nested scope as a sibling)
        return _scope(elt, parent, list_path, path)
    if isinstance(elt, list) and all(isinstance(x, dict) for x in elt):
        # shex.js, a nested scope with no own bindings whose one list was unwrapped
        return _scope([{}, elt], parent, list_path, path)
    raise BindingTreeError(f"not an iteration: {_short(elt)}")


def _short(x) -> str:
    s = repr(x)
    return s if len(s) < 120 else s[:117] + "..."


class ScopeTree:
    """A parsed tree plus the two indexes materialization needs."""

    def __init__(self, tree) -> None:
        self.root = parse_scope(tree)
        self.bound_at: dict[str, ListPath] = {}
        self.bindings = 0
        for s in self.root.walk():
            for v in s.own:
                self.bindings += 1
                at = self.bound_at.setdefault(v, s.list_path)
                if at != s.list_path:
                    raise BindingTreeError(f"variable {v} is bound at two lists, {at} and {s.list_path}")

    def variables(self) -> set[str]:
        return set(self.bound_at)
