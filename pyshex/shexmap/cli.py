"""``shexmap``: map RDF from one ShEx schema to another from the command line.

Bind and materialize in one step::

    shexmap -i data.ttl -s in.shex -f <tag:obs1> -t out.shex -r <tag:out1>

Only collect bindings (written as JSON, compatible with shex.js)::

    shexmap -i data.ttl -s in.shex -f <tag:obs1> -b bindings.json

Materialize from bindings saved earlier, by this tool or by shex.js::

    shexmap -j bindings.json -t out.shex -r <tag:out1>
"""
import json
import sys
from argparse import ArgumentParser
from pathlib import Path

from rdflib import BNode, Graph, URIRef

from pyshex.shexmap import (MapFunctionError, MapValidationError, MaterializationError, ThreadedMaterializer, bind,
                            dumps, loads)
from pyshex.shexmap.bindings import term_from_json


def parse_node(text: str):
    text = text.strip()
    if text.startswith('_:'):
        return BNode(text[2:])
    if text.startswith('<') and text.endswith('>'):
        text = text[1:-1]
    return URIRef(text)


def genargs(prog: str | None = None) -> ArgumentParser:
    p = ArgumentParser(prog, description="Map RDF between ShEx schemas with ShExMap (%Map:{ %}) annotations.")
    p.add_argument("-i", "--input", help="input RDF file or URL")
    p.add_argument("--input-format", default="turtle", help="input RDF format (default: turtle)")
    p.add_argument("-s", "--input-schema", help="input ShExC schema")
    p.add_argument("-f", "--focus", help="input node to map: <iri>, iri or _:label")
    p.add_argument("--start", help="input shape label (default: the input schema's start)")
    p.add_argument("-j", "--bindings", help="read bindings JSON instead of validating input")
    p.add_argument("-b", "--bindings-out", help="write the bindings as JSON ('-' for stdout)")
    p.add_argument("-t", "--output-schema", help="output ShExC schema")
    p.add_argument("-r", "--root", help="output node to build: <iri>, iri or _:label (default: a blank node)")
    p.add_argument("--output-start", help="output shape label (default: the output schema's start)")
    p.add_argument("--static", help="JSON object of extra variable values, as shex.js staticVars")
    p.add_argument("--strict", action="store_true",
                   help="fail when the input or the output can be matched in more than one way")
    p.add_argument("-o", "--output", help="write the output RDF here (default: stdout)")
    p.add_argument("--output-format", default="turtle", help="output RDF format (default: turtle)")
    return p


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = genargs(prog)
    opts = parser.parse_args(argv)
    if opts.bindings:
        if opts.input or opts.input_schema or opts.focus:
            parser.error("--bindings replaces --input, --input-schema and --focus")
    elif not (opts.input and opts.input_schema and opts.focus):
        parser.error("give --input, --input-schema and --focus, or --bindings")
    if not opts.output_schema and not opts.bindings_out:
        parser.error("nothing to do: give --output-schema and/or --bindings-out")

    try:
        if opts.bindings:
            bindings = loads(Path(opts.bindings).read_text(encoding="utf-8"))
        else:
            g = Graph().parse(opts.input, format=opts.input_format)
            bindings = bind(g, Path(opts.input_schema).read_text(encoding="utf-8"), parse_node(opts.focus),
                            start=opts.start, strict=opts.strict)
            if bindings.ambiguous:
                print(f"shexmap: warning: the input matches in {bindings.alternatives} ways that bind differently;"
                      " using the first (--strict makes this an error)", file=sys.stderr)
        if opts.bindings_out:
            text = dumps(bindings, indent=2) + "\n"
            if opts.bindings_out == "-":
                sys.stdout.write(text)
            else:
                Path(opts.bindings_out).write_text(text, encoding="utf-8")
        if opts.output_schema:
            static = {k: term_from_json(v) for k, v in json.loads(Path(opts.static).read_text(encoding="utf-8")).items()} \
                if opts.static else None
            m = ThreadedMaterializer(Path(opts.output_schema).read_text(encoding="utf-8"), static_vars=static)
            triples = m.materialize(bindings, parse_node(opts.root) if opts.root else BNode(), start=opts.output_start)
            if len(m.accepts) > 1:
                if opts.strict:
                    raise MaterializationError(f"the bindings fit the output schema in {len(m.accepts)} ways")
                print(f"shexmap: warning: the bindings fit the output schema in {len(m.accepts)} ways;"
                      " using the one that uses the most bindings", file=sys.stderr)
            out = Graph()
            for prefix, ns in m.prefixes.items():
                out.bind(prefix, ns, override=False)
            for t in triples:
                out.add(t)
            text = out.serialize(format=opts.output_format)
            if opts.output:
                Path(opts.output).write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
    except (MapValidationError, MaterializationError, MapFunctionError) as e:
        print(f"shexmap: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
