import os
import unittest

from rdflib import URIRef

from ancillary.earlreport import EARLPage
from tests.utils.manifest_tester import ManifestEntryTestCase


class ManifestShexShexCTestCase(ManifestEntryTestCase):
    def __init__(self, methodname):
        # This is a spot that you can insert conditional skips -- the second parameter below is a dictionary of test
        # names and skip reasons.
        # Example: skips = {'1val1STRING_LITERAL1_with_all_punctuation_pass': issue_text}
        super().__init__(methodname, None)

    def test_shex_shexc(self):
        self.mfst.shex_format = "shex"
        self.do_test()

    def test_generate_earl_report(self):
        self.mfst.schema_loader.schema_format = "shex"
        earlpage = EARLPage(URIRef("https://github.com/hsolbrig"))
        self.do_test(earlpage)
        earl_report = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data', 'earl_report.ttl')
        earlpage.g.serialize(earl_report, format="turtle")
        print(f"EARL report generated in {earl_report}")

if __name__ == '__main__':
    unittest.main()
