import os

from rdflib import URIRef

from ancilliary.earlreport import EARLPage
from tests.utils.manifest_tester import ManifestEntryTestCase


class TestManifestShexShexCTestCase(ManifestEntryTestCase):
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
