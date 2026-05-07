import os

from rdflib import Graph

TTL_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'Is1_Ip1_L_with_REGEXP_escapes_bare.ttl'))


def test_crlf_linefeeds_not_stripped():
    """Make sure that the data is being read in raw form -- that linefeeds aren't being stripped."""
    g = Graph()
    g.parse(TTL_FILE, format='turtle')
    assert list(g.objects())[0].value == '/\t\n\r-\\a𝒸'