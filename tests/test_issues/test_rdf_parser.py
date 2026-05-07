import os

from rdflib import Graph

from tests import datadir


"""
Test for an error in the RDFLIB parser. To fix the bug in rdflib 4.2.2:
> rdflib.plugins.parsers.notation3.py

1578            k = 'abfrtvn\\"\''.find(ch)
                if k >= 0:
                    uch = '\a\b\f\r\t\v\n\\"\''[k]
"""

RDF_FILE = os.path.join(datadir, 'validation', 'Is1_Ip1_LSTRING_LITERAL1_with_all_punctuation.ttl')


def test_rdflib_parser_handles_all_punctuation() -> None:
    """rdflib 4.2.2 bug: notation3 parser failed on certain escape sequences."""
    with open(RDF_FILE, 'rb') as f:
        rdf = f.read().decode()
    Graph().parse(data=rdf, format="turtle")  # passes if no exception is raised