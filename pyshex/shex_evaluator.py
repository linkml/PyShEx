import sys
from argparse import ArgumentParser
from typing import Optional, Union, List, NamedTuple, Type, Iterator, Callable

from CFGraph import CFGraph
from ShExJSG import ShExJ, ShExC
from rdflib import Graph, URIRef, RDF
from rdflib.util import guess_format
from sparqlslurper import QueryResultPrinter

from pyshex import PrefixLibrary
from pyshex.shape_expressions_language.p5_2_validation_definition import isValid
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import FixedShapeMap, ShapeAssociation, START, \
    START_TYPE
from pyshex.user_agent import UserAgent, SlurpyGraphWithAgent
from pyshex.utils.schema_loader import SchemaLoader
from pyshex.utils.sparql_query import SPARQLQuery


class EvaluationResult(NamedTuple):
    result: bool
    focus: Optional[URIRef]
    start: Optional[URIRef]
    reason: Optional[str]


# Handy types
URI = Union[str, URIRef]        # URI as an argument
URILIST = Iterator[URI]             # List of URI's as an argument
URIPARM = Union[URI, URILIST]       # Choice of URI or list
STARTPARM = [Union[Type[START], START_TYPE, URILIST]]


def normalize_uri(u: URI) -> URIRef:
    """ Return a URIRef for a str or URIRef """
    return u if isinstance(u, URIRef) else URIRef(str(u))


def normalize_urilist(ul: URILIST) -> List[URIRef]:
    """ Return a list of URIRefs for ul """
    return [normalize_uri(u) for u in ul]


def normalize_uriparm(p: URIPARM) -> List[URIRef]:
    """ Return an optional list of URIRefs for p"""
    return normalize_urilist(p) if isinstance(p, List) else \
        normalize_urilist([p]) if isinstance(p, (str, URIRef)) else p


def normalize_startparm(p: STARTPARM) -> List[Union[type(START), START_TYPE, URIRef]]:
    """ Return the startspec for p """
    if not isinstance(p, list):
        p = [p]
    return [normalize_uri(e) if isinstance(e, str) and e is not START else e for e in p]


class ShExEvaluator:
    """ Shape Expressions Evaluator """

    def __init__(self,
                 rdf: Optional[Union[str, Graph]] = None,
                 schema: Optional[Union[str, ShExJ.Schema]] = None,
                 focus: Optional[URIPARM] = None,
                 start: STARTPARM = None,
                 rdf_format: str = "turtle",
                 debug: bool = False,
                 debug_slurps: bool = False,
                 over_slurp: bool = None,
                 output_sink: Optional[Callable[[EvaluationResult], bool]] = None) -> None:
        """ Evaluator constructor.  All of the parameters below can be set in the constructor or at runtime

        :param rdf: RDF string, file name, URL or Graph for evaluation.
        :param schema: ShEx Schema to evaluate. Can be ShExC, ShExJ or a pre-parsed schema
        :param focus: focus node(s).  If absent, all non-BNode subjects in the graph are evaluated
        :param start: start node(s). If absent, the START node in the schema is used
        :param rdf_format: format for RDF. Default: "Turtle"
        :param debug: emit semi-helpful debug information
        :param debug: debug graph fetch calls
        :param over_slurp: Controls whether SPARQL slurper does exact or over slurps
        :param output_sink: Function for accepting evaluation results and returns whether to keep evaluating
        """
        self.pfx: PrefixLibrary = None
        self.rdf_format = rdf_format
        self.g = None
        self.rdf = rdf
        self._schema = None
        self.schema = schema
        self._focus = None
        self.focus = focus
        self.start = start
        self.debug = debug
        self.debug_slurps = debug_slurps
        self.over_slurp = over_slurp
        self.output_sink = output_sink
        self.nerrors = 0
        self.nnodes = 0
        self.eval_result = []

    @property
    def rdf(self) -> str:
        """

        :return: The rendering of whatever RDF is currently being evaluated
        """
        return self.g.serialize(format=self.rdf_format).decode()

    @rdf.setter
    def rdf(self, rdf: Optional[Union[str, Graph]]) -> None:
        """ Set the RDF DataSet to be evaluated.  If ``rdf`` is a string, the presence of a return is the
        indicator that it is text instead of a location.

        :param rdf: File name, URL, representation of rdflib Graph
        """
        if isinstance(rdf, Graph):
            self.g = rdf
        else:
            self.g = Graph()
            if isinstance(rdf, str):
                if '\n' in rdf or '\r' in rdf:
                    self.g.parse(data=rdf, format=self.rdf_format)
                elif ':' in rdf:
                    self.g.parse(location=rdf, format=self.rdf_format)
                else:
                    self.g.parse(source=rdf, format=self.rdf_format)

    @property
    def schema(self) -> Optional[str]:
        """

        :return: The ShExC representation of the schema if one is supplied
        """
        return str(ShExC(self._schema)) if self._schema else None

    @schema.setter
    def schema(self, shex: Optional[Union[str, ShExJ.Schema]]) -> None:
        """ Set the schema to be used.  Schema can either be a ShExC or ShExJ string or a pre-parsed schema.

        :param shex:  Schema
        """
        self.pfx = None
        if shex is not None:
            if isinstance(shex, ShExJ.Schema):
                self._schema = shex
            else:
                shext = shex.strip()
                loader = SchemaLoader()
                if ('\n' in shex or '\r' in shex) or shext[0] in '#<_: ':
                    self._schema = loader.loads(shex)
                else:
                    self._schema = loader.load(shex) if isinstance(shex, str) else shex
                if self._schema is None:
                    raise ValueError("Unable to parse shex file")
                self.pfx = PrefixLibrary(loader.schema_text)

    @property
    def focus(self) -> Optional[List[URIRef]]:
        """
        :return: The list of focus nodes (if any)
        """
        return self._focus

    @property
    def foci(self) -> List[URIRef]:
        """

        :return: The current set of focus nodes
        """
        return self._focus if self._focus else sorted([s for s in set(self.g.subjects()) if isinstance(s, URIRef)])

    @focus.setter
    def focus(self, focus: Optional[URIPARM]) -> None:
        """ Set the focus node(s).  If no focus node is specified, the evaluation will occur for all non-BNode
        graph subjects.  Otherwise it can be a string, a URIRef or a list of string/URIRef combinations

        :param focus: None if focus should be all URIRefs in the graph otherwise a URI or list of URI's
        """
        self._focus = normalize_uriparm(focus) if focus else None

    @property
    def start(self) -> STARTPARM:
        """

        :return: The schema start node(s)
        """
        return self._start

    @start.setter
    def start(self, start: STARTPARM) -> None:
        self._start = normalize_startparm(start) if start else [START]

    def evaluate(self,
                 rdf: Optional[Union[str, Graph]] = None,
                 shex: Optional[Union[str, ShExJ.Schema]] = None,
                 focus: Optional[URIPARM] = None,
                 start: STARTPARM = None,
                 rdf_format: Optional[str] = None,
                 debug: Optional[bool] = None,
                 debug_slurps: Optional[bool] = None,
                 over_slurp: Optional[bool] = None,
                 output_sink: Optional[Callable[[EvaluationResult], bool]] = None) -> List[EvaluationResult]:
        if rdf is not None or shex is not None or focus is not None or start is not None:
            evaluator = ShExEvaluator(rdf=rdf if rdf is not None else self.g,
                                      schema=shex if shex is not None else self._schema,
                                      focus=focus if focus is not None else self.focus,
                                      start=start if start is not None else self.start if self.start else START,
                                      rdf_format=rdf_format if rdf_format is not None else self.rdf_format,
                                      output_sink=output_sink if output_sink is not None else self.output_sink)
        else:
            evaluator = self

        self.eval_result = []
        if evaluator.output_sink is None:
            def sink(e: EvaluationResult) -> bool:
                self.eval_result.append(e)
                return True
            evaluator.output_sink = sink

        processing = True
        self.nerrors = 0
        self.nnodes = 0
        if START in evaluator.start and evaluator._schema.start is None:
            self.nerrors += 1
            evaluator.output_sink(EvaluationResult(False, None, None, 'START node is not specified'))
            return self.eval_result

        # Experimental -- xfer all ShEx namespaces to g
        if self.pfx and evaluator.g is not None:
            self.pfx.add_bindings_to(evaluator.g)

        cntxt = Context(evaluator.g, evaluator._schema)
        cntxt.debug_context.debug = debug if debug is not None else self.debug
        cntxt.debug_context.trace_slurps = debug_slurps if debug_slurps is not None else self.debug_slurps
        cntxt.over_slurp = self.over_slurp if over_slurp is not None else self.over_slurp

        for focus in evaluator.foci:
            self.nnodes += 1
            start_list: List[Union[URIRef, START]] = []
            for start in evaluator.start:
                if start is START:
                    start_list.append(evaluator._schema.start)
                elif isinstance(start, START_TYPE):
                    start_list += list(evaluator.g.objects(focus, start.start_predicate))
                else:
                    start_list.append(start)
            if start_list:
                for start_node in start_list:
                    map_ = FixedShapeMap()
                    map_.add(ShapeAssociation(focus, start_node))
                    cntxt.reset()
                    success, fail_reasons = isValid(cntxt, map_)
                    if not success:
                        self.nerrors += 1
                    if not evaluator.output_sink(EvaluationResult(success, focus, start_node,
                                                                  '\n'.join(fail_reasons) if not success else '')):
                        processing = False
                        break
            else:
                self.nerrors += 1
                evaluator.output_sink(EvaluationResult(False, focus, None, "No start node located"))
            if not processing:
                break
        return self.eval_result


def genargs(prog: Optional[str] = None) -> ArgumentParser:
    """
    Create a command line parser
    :return: parser
    """
    parser = ArgumentParser(prog)
    parser.add_argument("rdf", help="Input RDF file or SPARQL endpoint if slurper or sparql options")
    parser.add_argument("shex", help="ShEx specification")
    parser.add_argument("-f", "--format", help="Input RDF Format", default="turtle")
    parser.add_argument("-s", "--start", help="Start shape. If absent use ShEx start node.")
    parser.add_argument("-ut", "--usetype", help="Start shape is rdf:type of focus", action="store_true")
    parser.add_argument("-sp", "--startpredicate", help="Start shape is object of this predicate")
    parser.add_argument("-fn", "--focus", help="RDF focus node")
    parser.add_argument("-A", "--allsubjects", help="Evaluate all non-bnode subjects in the graph", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true", help="Add debug output")
    parser.add_argument("-ss", "--slurper", action="store_true", help="Use SPARQL slurper graph")
    parser.add_argument("-ssg", "--gdbslurper", action="store_true", help="Use GraphDB specific slurper to "
                                                                          "persistent BNodes")
    parser.add_argument("-cf", "--flattener", action="store_true", help="Use RDF Collections flattener graph")
    parser.add_argument("-sq", "--sparql", help="SPARQL query to generate focus nodes")
    parser.add_argument("-se", "--stoponerror", help="Stop on an error", action="store_true")
    parser.add_argument("--stopafter", help="Stop after N nodes", type=int)
    parser.add_argument("-ps", "--printsparql", help="Print SPARQL queries as they are executed", action="store_true")
    parser.add_argument("-pr", "--printsparqlresults", help="Print SPARQL query and results", action="store_true")
    parser.add_argument("-gn", "--graphname", help="Specific SPARQL graph to query - use '' for any named graph")
    parser.add_argument("-pb", "--persistbnodes", help="Treat BNodes as persistent in SPARQL endpoint",
                        action="store_true"),
    parser.add_argument("--useragent", help='Use this user agent in the SPARQL Queries (Default: "' + UserAgent + '")')
    return parser


def evaluate_cli(argv: Optional[Union[str, List[str]]] = None, prog: Optional[str] = None) -> int:
    if isinstance(argv, str):
        argv = argv.split()
    opts = genargs(prog).parse_args(argv if argv is not None else sys.argv[1:])
    if opts.sparql or opts.gdbslurper:
        opts.slurper = True
    if opts.slurper and opts.flattener:
        print("Error: Cannot combine slurper and flattener graphs", file=sys.stderr)
        return 2
    if not opts.sparql and not opts.slurper and \
            (opts.printsparql or opts.printsparqlresults or opts.graphname is not None or opts.persistbnodes):
        print("Error: printsparql, pringsparqlresults, graphname and persistbnodes are SPARQL only",
              file=sys.stderr)
    if not opts.format:
        opts.format = guess_format(opts.rdf)
    if not opts.format:
        print('Error: Cannot determine RDF format from file name - use "--format" option', file=sys.stderr)
        return 3
    if opts.slurper or opts.gdbslurper:
        g = SlurpyGraphWithAgent(opts.rdf, agent=opts.useragent, gdb_slurper=opts.gdbslurper)
        if opts.printsparql:
            g.debug_slurps = True
        if opts.printsparqlresults:
            g.debug_slurps = True
            g.add_result_hook(QueryResultPrinter)
        if opts.graphname is not None:
            g.graph_name = opts.graphname
        if opts.persistbnodes:
            g.persistent_bnodes = True
    else:
        g = CFGraph() if opts.flattener else Graph()
        if '\n' in opts.rdf or '\r' in opts.rdf:
            g.parse(data=opts.rdf, format=opts.format)
        else:
            g.parse(opts.rdf, format=opts.format)

    if not (opts.focus or opts.allsubjects or opts.sparql):
        print('Error: You must specify one or more graph focus nodes, supply a SPARQL query, or use the "-A" option',
              file=sys.stderr)
        return 4

    start = []
    if opts.start:
        start.append(opts.start)
    if opts.usetype:
        start.append(START_TYPE(RDF.type))
    if opts.startpredicate:
        start.append(START_TYPE(opts.startpredicate))
    if not start:
        start.append(START)
    if opts.sparql:
        # TODO: switch to a generator idiom all the way through
        if opts.focus is None:
            opts.focus = []
        elif not isinstance(opts.focus, list):
            opts.focus = [opts.focus]
        opts.focus += list(SPARQLQuery(opts.rdf, opts.sparql, print_query=opts.printsparql,
                                       print_results=opts.printsparqlresults, user_agent=opts.useragent).focus_nodes())

    def result_sink(rslt: EvaluationResult) -> bool:
        if not rslt.result:
            if evaluator.nerrors == 1:
                print("Errors:")
            else:
                print()
            print(f"  Focus: {rslt.focus}\n  Start: {rslt.start}\n  Reason: {str(rslt.reason)}")
            return not opts.stoponerror and (not opts.stopafter or evaluator.nnodes < opts.stopafter)
        return not opts.stopafter or evaluator.nnodes < opts.stopafter

    evaluator = ShExEvaluator(g, opts.shex, opts.focus, start, rdf_format=opts.format, debug=opts.debug,
                              output_sink=result_sink)
    evaluator.evaluate()
    return 1 if evaluator.nerrors else 0


if __name__ == '__main__':
    evaluate_cli(sys.argv[1:])
