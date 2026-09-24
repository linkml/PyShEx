"""ShExMap: map RDF from one ShEx schema to another.

A port of the ideas in shex.js's ``@shexjs/extension-map``.  Semantic actions in the
``http://shex.io/extensions/Map/#`` extension annotate triple constraints:

* in the **input** schema, ``%Map:{ bp:given %}`` binds the variable ``bp:given`` to the
  value the triple constraint matched, and ``%Map:{ regex(/(?<bp:family>...)/) %}`` or
  ``%Map:{ hashmap(var, {...}) %}`` bind variables computed from it;
* in the **output** schema, the same annotations say where each bound value goes.

>>> bindings = bind(input_graph, input_shexc, focus)          # doctest: +SKIP
>>> output_graph = materialize(output_shexc, bindings, root)  # doctest: +SKIP

or both at once with :func:`map_graph`.  The ``shexmap`` command does the same from a
terminal.
"""
from rdflib import Graph
from rdflib.term import Node

from pyshex.shexmap.bindings import (MAP_EXTENSION, BindingNode, MapValidationError, bind, dumps, loads,
                                     shexc_prefixes)
from pyshex.shexmap.functions import MapFunctionError
from pyshex.shexmap.materializer import Binder, MaterializationError, materialize
from pyshex.shexmap.semact import register

__all__ = ["MAP_EXTENSION", "BindingNode", "Binder", "MapFunctionError", "MapValidationError",
           "MaterializationError", "bind", "dumps", "loads", "map_graph", "materialize", "register",
           "shexc_prefixes"]


def map_graph(graph: Graph, input_schema, focus: str | Node, output_schema, root: str | Node,
              start=None, output_start=None, static_vars=None) -> Graph:
    """Bind ``focus`` against ``input_schema`` and materialize ``root`` in ``output_schema``."""
    return materialize(output_schema, bind(graph, input_schema, focus, start=start), root,
                       start=output_start, static_vars=static_vars)
