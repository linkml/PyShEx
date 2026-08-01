
# True means refresh all test files (only partially implemented at the moment)
import os

refresh_files = False

# True means that we skip all tests that go outside our own environment (e.g. wikidata, etc)
# You can set this to True, False or base it on the present of a file in the root directory called "tests/data/SKIP_EXTERNAL_URLS"
# Must be a real bool: a string handed to pytest.mark.skipif gets eval'ed as a Python expression
_skip_env = os.environ.get('SKIP_EXTERNAL_URLS', None)
SKIP_EXTERNAL_URLS_MSG = "External url's are not tested - set tests.__init__.py.SKIP_EXTERNAL_URLS to False to run"

datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
if _skip_env is None:
    SKIP_EXTERNAL_URLS = os.path.exists(os.path.join(datadir, 'SKIP_EXTERNAL_URLS'))
else:
    SKIP_EXTERNAL_URLS = _skip_env.lower() not in ('', '0', 'false', 'no')

print("Skipping external URL tests" if SKIP_EXTERNAL_URLS else "Including external URLs in tests")

# Settings for rdflib parsing issue

#         See line 1578 in notation3.py:
#                 k = 'abfrtvn\\"\''.find(ch)
#                 if k >= 0:
#                     uch = '\a\b\f\r\t\v\n\\"\''[k]
from rdflib import __version__ as rdflib_version
assert rdflib_version >= "5.0.0", "rdflib version 5.0.0 or greater is required"
