# Python implementation of ShEx 2.0
[![Pyversions](https://img.shields.io/pypi/pyversions/PyShEx.svg)](https://pypi.python.org/pypi/PyShEx)

[![PyPi](https://img.shields.io/pypi/v/PyShEx.svg)](https://pypi.python.org/pypi/PyShEx)


[![DOI](https://zenodo.org/badge/116042298.svg)](https://zenodo.org/badge/latestdoi/116042298)

[![CodeCov](https://codecov.io/gh/hsolbrig/PyShEx/branch/main/graph/badge.svg)](https://codecov.io/gh/hsolbrig/PyShEx)

https://mybinder.org/v2/gh/hsolbrig/pyshex/master

This package is a reasonably literal implementation of the [Shape Expressions Language 2.0](http://shex.io/shex-semantics/).  It can parse and "execute" ShExC and ShExJ source.

## Revisions
* 0.2.dev3 -- added SchemaEvaluator and other tweaks.  There are still some unit tests that fail -- beware
* 0.3.0 -- Fix several issues.  Still does not pass all unit tests -- see `test_manifest.py` for details
* 0.4.0 -- Added sparql_slurper capabilities. 
* 0.4.1 -- Resolves several issues with reactome and disease test cases
* 0.4.2 -- Fix issues #13 (missing start) and #14 (Inconsistent shape causes loop)
* 0.4.3 -- Fix issues #16 and #15 and some refactoring
* 0.5.0 -- First cut at returning fail reasons... some work still needed
* 0.5.1 -- Update shexc parser to include multi-line comments and bug fixes
* 0.5.2 -- Issue with installer - missed the parse_tree package
* 0.5.3 -- make sparql_slurper a dependency
* 0.5.4 -- Fixed long recursion issue with blood pressure example
* 0.5.5 -- Fixed zero cardinality issue (#20)
* 0.5.6 -- Added CLI entry point and cleaned up error reporting
* 0.5.7 -- Throw an error on an invalid focus node (#23)
* 0.5.9 -- Candidate for ShEx 2.1
* 0.5.10 -- Fixed evaluator to load files, strings, etc. as ShEx
* 0.5.11 -- Added Collections Flattening graph option to evaluator.
* 0.5.12 -- Added -A option, catch missing start node early
* 0.6.0 -- Added the -ut and -sp options to allow start nodes to be specified by rdf:type or an arbitrary predicate
* 0.6.1 -- Added the ability to supply a SPARQL Query (-sq option) 
* 0.7.0 -- Fixes for issues 28, 29 and 30 
* 0.7.1 -- Fix issue 26
* 0.7.2 -- Upgrade error reporting
* 0.7.3 -- Report using namespaces, enhance PrefixLib to inject into a module
* 0.7.4 -- Added '-ps', '-pr', '-gn', '-pb' options to CLI
* 0.7.5 -- Fix CLOSED issue in evaluate call (issue 41)
* 0.7.6 -- bump version due to build error

## Installation
```bash
pip install PyShEx
```
Note: If you need to escape single quotes in RDF literals, you will need to install the bleeding edge
of rdflib:
```bash
pip uninstall rdflib
pip install git+https://github.com/rdflib/rdflib
```
Unfortunately, however, `rdflib-jsonld` is NOT compatible with the bleeding edge rdflib, so you can't use a json-ld parser in this situation.

## shexeval CLI
```bash
> shexeval -h
usage: shexeval [-h] [-f FORMAT] [-s START] [-ut] [-sp STARTPREDICATE]
                [-fn FOCUS] [-A] [-d] [-ss] [-cf] [-sq SPARQL] [-se]
                [--stopafter STOPAFTER] [-ps] [-pr] [-gn GRAPHNAME] [-pb]
                rdf shex

positional arguments:
  rdf                   Input RDF file or SPARQL endpoint if slurper or sparql
                        options
  shex                  ShEx specification

optional arguments:
  -h, --help            show this help message and exit
  -f FORMAT, --format FORMAT
                        Input RDF Format
  -s START, --start START
                        Start shape. If absent use ShEx start node.
  -ut, --usetype        Start shape is rdf:type of focus
  -sp STARTPREDICATE, --startpredicate STARTPREDICATE
                        Start shape is object of this predicate
  -fn FOCUS, --focus FOCUS
                        RDF focus node
  -A, --allsubjects     Evaluate all non-bnode subjects in the graph
  -d, --debug           Add debug output
  -ss, --slurper        Use SPARQL slurper graph
  -cf, --flattener      Use RDF Collections flattener graph
  -sq SPARQL, --sparql SPARQL
                        SPARQL query to generate focus nodes
  -se, --stoponerror    Stop on an error
  --stopafter STOPAFTER
                        Stop after N nodes
  -ps, --printsparql    Print SPARQL queries as they are executed
  -pr, --printsparqlresults
                        Print SPARQL query and results
  -gn GRAPHNAME, --graphname GRAPHNAME
                        Specific SPARQL graph to query - use '' for any named
                        graph
  -pb, --persistbnodes  Treat BNodes as persistent in SPARQL endpoint
```

## Documentation
See: [examples](notebooks) Jupyter notebooks for sample uses


## General Layout
The root `pyshex` package is subdivided into:

* [shape_expressions_language](pyshex/shape_expressions_language) - implementation of the various sections in  [Shape Expressions Language 2.0](http://shex.io/shex-semantics/).  As an example, [3. Terminology](http://shex.io/shex-semantics/#terminology) is implemented in [p3_terminology.py](pyshex/shape_expressions_language/p3_terminology.py), [5.2 Validation Definition](http://shex.io/shex-semantics/#validation) in [p5_2_validation_definition.py](pyshex/shape_expressions_language/p5_2_validation_definition.py), etc.
* [shapemap_structure_and_language](pyshex/shapemap_structure_and_language) - implementation of [ShapeMap Structure and Language](http://shex.io/shape-map/) (as well as we can understand it)
* [sparql11_query](pyshex/sparql11_query) - required sections from [SPARQL 1.1 Query Language section 17.2](https://www.w3.org/TR/sparql11-query/#operandDataTypes)
* [utils](pyshex/utils) - supporting utilities

The ShEx schema definitions for this package come from [ShExJSG](https://github.com/hsolbrig/ShExJSG)

We are trying to keep the python as close as possible to the (semi-)formal specification.  As an example, the statement:
```text
Se is a ShapeAnd and for every shape expression se2 in shapeExprs, satisfies(n, se2, G, m)
```
is implemented in Python as:
```python
        ...
if isinstance(se, ShExJ.ShapeAnd):
    return satisfiesShapeAnd(cntxt, n, se)
        ...
def satisfiesShapeAnd(cntxt: Context, n: nodeSelector, se: ShExJ.ShapeAnd) -> bool:
    return all(satisfies(cntxt, n, se2) for se2 in se.shapeExprs)
```

## Dependencies
This package is built using:
* [ShExJSG](https://github.com/hsolbrig/ShExJSG) -- an object representation of the ShEx AST as defined by [ShEx.jsg](https://github.com/shexSpec/shexTest/blob/master/doc/ShExJ.jsg) and compiled through the [PyJSG](https://github.com/hsolbrig/pyjsg) compiler.
* The python [ShExC](https://github.com/shexSpec/grammar/tree/master/parsers/python) compiler -- which transforms the [Shape Expressions Language](http://shex.io/shex-semantics/index.html) into ShExJSG images.
* [rdflib](https://rdflib.readthedocs.io/en/stable/) 


## Conformance

This implementation passes all of the tests in the master branch of [validation/manifest.ttl](https://raw.githubusercontent.com/shexSpec/shexTest/master/validation/manifest.ttl) with the following exceptions:

At the moment, there are 1088 tests, of which:

* 1007 pass
* 81 are skipped - reasons:
1) (52) sht:LexicalBNode, sht:ToldBNode and sht:BNodeShapeLabel test non-blank blank nodes (`rdflib` does not preserve bnode "identity")
2) (18) sht:Import Uses ShEx 2.1 IMPORT feature -- not yet implemented (three aren't tagged)
3) (3) Uses manifest shapemap feature -- not yet implemented
4) (2) sht:relativeIRI -- this isn't a real problem, but we haven't taken time to deal with this in the test harness
5) (6) `rdflib` has a parsing error when escaping single quotes. (Issue submitted, awaiting release)

As mentioned above, at the moment this is as literal an implementation of the specification as was sensible.  This means, in particular, that we are less than clever when it comes to partition management.

## Docker

### Build

```shell
docker build -t pyshex docker
```

### Run

```shell
docker run --rm -it pyshex -gn '' -ss -ut -pr -sq 'select distinct ?item where{?item a <http://w3id.org/biolink/vocab/Gene>} LIMIT 1' http://graphdb.dumontierlab.com/repositories/ncats-red-kg https://github.com/biolink/biolink-model/raw/master/shex/biolink-modelnc.shex
```

