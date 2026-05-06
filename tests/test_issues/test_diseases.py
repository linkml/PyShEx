import os

import pytest

from tests import SKIP_EXTERNAL_URLS, SKIP_EXTERNAL_URLS_MSG
from tests.utils.wikidata_utils import WikiDataTestCase


@pytest.mark.skipif(SKIP_EXTERNAL_URLS, reason=SKIP_EXTERNAL_URLS_MSG)
class TestWikiDiseases(WikiDataTestCase):
    """Test a sample conformance checker for the WikiData disease structure."""

    # This will change over time - expected values for the first 8 results
    expected_results = [True, True, True, True, True, True, True, True]

    def test_diseases(self):
        test_data_base = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'wikidata', 'disease'))

        rslts = self.run_test(
            "https://raw.githubusercontent.com/SuLab/Genewiki-ShEx/master/diseases/manifest_100.json",
            num_entries=8, debug=False, debug_slurps=False, save_graph_dir=test_data_base,
        )
        for rslt in rslts:
            print(f"{'CONFORMS' if rslt.result else 'FAIL'}: {rslt.focus}")

        assert all(expected == actual
                   for expected, actual in zip(self.expected_results, [r.result for r in rslts]))