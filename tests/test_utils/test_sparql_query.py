from pyshex.utils.sparql_query import SPARQLQuery
from tests import datadir
import pytest

@pytest.mark.skip("SPARQL query, sometimes URL is down. Need to look for an alternative.")
def test_basics():


    q = SPARQLQuery(
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/sparql",
        datadir / "t1.sparql" if hasattr(datadir, "__truediv__") else datadir + "/t1.sparql",
    )

    expected = [
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00001",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00002",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00003",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00004",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00005",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00006",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00007",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00008",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00009",
        "http://wifo5-04.informatik.uni-mannheim.de/drugbank/resource/drugs/DB00010",
    ]

    assert [str(f) for f in q.focus_nodes()] == expected