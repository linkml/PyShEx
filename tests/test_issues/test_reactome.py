import os
import pytest

from tests import SKIP_EXTERNAL_URLS, SKIP_EXTERNAL_URLS_MSG
from tests.utils.wikidata_utils import WikiDataTestCase

EXPECTED_RESULTS = [True, False, False, False, False, True, False, False]
TEST_DATA_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'wikidata', 'reactome'))
MANIFEST_URL = "https://raw.githubusercontent.com/shexSpec/schemas/master/Wikidata/pathways/Reactome/manifest_all.json"


@pytest.mark.skipif(SKIP_EXTERNAL_URLS, reason=SKIP_EXTERNAL_URLS_MSG)
def test_wikidata_reactome() -> None:
    # This will change over time - expected values for the first 8 results
    # Note: This test has never been run past 1
    helper = WikiDataTestCase()
    rslts = helper.run_test(MANIFEST_URL, num_entries=1, debug=False, debug_slurps=False,
                            save_graph_dir=TEST_DATA_BASE)
    for rslt in rslts:
        print(f"{'CONFORMS' if rslt.result else 'FAIL'}: {rslt.focus}")

    assert all(expected == actual
               for expected, actual in zip(EXPECTED_RESULTS, [r.result for r in rslts]))