from functools import lru_cache
from typing import Optional

import requests

from tests import SKIP_EXTERNAL_URLS

# Various test locations
DRUGBANK_SPARQL_URL = 'http://wifo5-04.informatik.uni-mannheim.de/drugbank/sparql'
BIOLINK_MODEL_URL = 'https://biolink.github.io/biolink-model/'
FHIRCAT_GRAPHDB_URL = 'https://graph.fhircat.org/repositories/fhirontology'
DUMONTIER_GRAPHDB_URL = 'http://graphdb.dumontierlab.com/repositories/ncats-red-kg'

PRE_CACHE = [
    DRUGBANK_SPARQL_URL,
    BIOLINK_MODEL_URL
]

@lru_cache()
def is_up(url: str) -> Optional[bool]:
    """ Determine whether url is up and running """
    if SKIP_EXTERNAL_URLS:
        return False
    try:
        resp = requests.head(url, timeout=2, allow_redirects=True)
    except Exception:
        return False
    # A gateway error or a missing repository means the endpoint can't answer queries
    return resp.status_code < 500 and resp.status_code != 404

def is_down_reason(url: str) -> str:
    svr_status = is_up(url)
    return f"Server {url} is {'UP' if svr_status else 'DOWN' if svr_status is False else 'NOT BEING TESTED'}"

# Prime the cache
for svr in PRE_CACHE:
    print(is_down_reason(svr))
