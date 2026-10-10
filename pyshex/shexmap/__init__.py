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

* :func:`bind` validates, then partitions each neighbourhood by exhaustive search;
  when the input conforms in several ways that bind differently it says so
  (``.alternatives``), and :func:`bind_all` returns every way.  EXTENDS and inverse
  (``^p``) constraints are followed.
* :func:`analyse` checks a schema pair before any data: every output repetition has a
  list to iterate, every variable read is bound where it can be read from, and unused
  bindings are reported.
* :class:`ThreadedMaterializer` builds the output from the binding tree's structure: an
  output repetition iterates the input list its variables are bound at, a parent's
  binding is read in every item, and the alternatives a ``OneOf`` or an extension leaves
  open are kept (``.accepts``), the one that reads the most bindings returned.
"""
from rdflib import Graph
from rdflib.term import Node

from pyshex.shexmap.bindings import (MAP_EXTENSION, NODE_KEY, AmbiguousBindingsError, Bindings, MapValidationError,
                                     bind, bind_all, dumps, loads, normalize, shexc_prefixes)
from pyshex.shexmap.analysis import Report, analyse
from pyshex.shexmap.functions import MapFunctionError
from pyshex.shexmap.materializer import Accept, MaterializationError, ThreadedMaterializer, materialize
from pyshex.shexmap.semact import register

__all__ = ["MAP_EXTENSION", "NODE_KEY", "Accept", "AmbiguousBindingsError", "Bindings", "MapFunctionError",
           "MapValidationError", "MaterializationError", "Report", "ThreadedMaterializer", "analyse", "bind",
           "bind_all", "dumps", "loads", "map_graph", "materialize", "normalize", "register", "shexc_prefixes"]


def map_graph(graph: Graph, input_schema, focus: str | Node, output_schema, root: str | Node | None = None,
              start=None, output_start=None, static_vars=None, strict: bool = False) -> Graph:
    """Bind ``focus`` against ``input_schema`` and materialize ``root`` in ``output_schema``."""
    return materialize(output_schema, bind(graph, input_schema, focus, start=start, strict=strict), root,
                       start=output_start, static_vars=static_vars)
