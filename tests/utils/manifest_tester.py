import unittest

import os
from typing import Dict, Optional

import sys
from ShExJSG import ShExJ
from rdflib import URIRef
import rdflib_shim
shimin = rdflib_shim.RDFLIB_SHIM

from ancillary.earlreport import EARLPage
from pyshex.shape_expressions_language.p5_2_validation_definition import isValid
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import ShapeAssociation, FixedShapeMap, START
from tests.utils.manifest import ShExManifest, SHT
from tests.utils.uri_redirector import URIRedirector

# TODO: Remove this whenever rdflib issue #124 is fixed (https://github.com/RDFLib/rdflib/issues/804)
sys.setrecursionlimit(1200)

ENTRY_NAME = ''                          # Individual element to test
START_AFTER = ''                         # Element to start at (or after)

CONTINUE_ON_FAIL = not(START_AFTER)
VERBOSE = False
DEBUG = bool(ENTRY_NAME) or bool(START_AFTER)
TEST_SKIPS_ONLY = False                     # Double check that all skips need skipping
USE_LOCAL_FILES = True                     # Use local files if possible

# Do Not Change this - must match manifest
REMOTE_FILE_LOC = "https://raw.githubusercontent.com/shexSpec/shexTest/master/"


# Local equivalent of online data files
# Note:
shextest_path = os.path.abspath(os.path.join(os.path.dirname(__file__),     # utils
                                             '..',                          # tests
                                             'data',                        # tests/data
                                             'shexTest'))                   # tests/data/shexTest

BASE_FILE_LOC = shextest_path if USE_LOCAL_FILES and os.path.exists(shextest_path) else REMOTE_FILE_LOC
BASE_FILE_LOC = BASE_FILE_LOC + ('/' if not BASE_FILE_LOC.endswith('/') else '')
print(f"*****> Running test from {BASE_FILE_LOC}\n")


# Reasons for skipping things
FOCUS_DATATYPE = "FocusDatatype"

skip_traits = [SHT.BNodeShapeLabel, SHT.ToldBNode, SHT.LexicalBNode, SHT.ShapeMap, SHT.Import, SHT.relativeIRI]

# We can't do an effective test on relative files when we're rewriting URI's
if BASE_FILE_LOC != REMOTE_FILE_LOC:
    skip_traits.append(SHT.relativeIRI)


class ManifestEntryTestCase(unittest.TestCase):
    """
    Base class for manifest tests
    """

    @classmethod
    def setUpClass(cls):
        cls.mfst = ShExManifest(os.path.join(BASE_FILE_LOC, 'validation', 'manifest.ttl'),
                                manifest_format="turtle")
        if BASE_FILE_LOC != REMOTE_FILE_LOC:
            cls.mfst.schema_loader.base_location = REMOTE_FILE_LOC
            cls.mfst.schema_loader.redirect_location = BASE_FILE_LOC
            cls.mfst.data_redirector = URIRedirector(URIRef(REMOTE_FILE_LOC), BASE_FILE_LOC)
            cls.mfst.schema_redirector = cls.mfst.data_redirector

        cls.started = not bool(START_AFTER)
        cls.npassed = 0
        cls.nskipped = 0
        cls.nfailed = 0
        cls.start_skipped = 0
        cls.skip_reasons: Dict[str, int] = {}

    def __init__(self, methodname: str=None, expected_failures: Dict[str, str]=None):
        super().__init__(methodname)
        self.expected_failures: Dict[str, str] = {} if expected_failures is None else expected_failures


    @staticmethod
    def URIname(uri: URIRef) -> str:
        return str(uri).replace(str(SHT), '')

    def add_earl(self, status: str, me_name: str) -> None:
        if self.earl_report:
            self.earl_report.add_test_result(me_name, status)

    def skip(self, me_name: str) -> None:
        self.nskipped += 1
        # Don't report skips - they show up as red "fails".  Omitting leaves black "untested"
        # self.add_earl('skipped', me_name)

    def fail(self, me_name: str) -> None:
        self.nfailed += 1
        self.add_earl('failed', me_name)

    def pass_(self, me_name: str) -> None:
        self.npassed += 1
        self.add_earl('passed', me_name)

    def eval_entry(self, entry_name: str) -> bool:
        mes = self.mfst.entries[entry_name]
        for me in mes:                          # There can be more than one entry per name...
            # Determine the start point
            if not self.started:
                if not me.name.startswith(START_AFTER):
                    self.start_skipped += 1
                    return True
                else:
                    self.started = True
                    if VERBOSE:
                        print(f"STARTED - Skipped {self.start_skipped} entries")

            # Determine whether this entry should be skipped
            should_skip = False

            # Skip
            skipped_traits = list(me.traits.intersection(skip_traits))
            if skipped_traits:
                if VERBOSE:
                    print(f"Skipping {me.name} ({', '.join([self.URIname(t) for t in me.traits])}) - Skipped trait")
                key = str(skipped_traits[0]).replace(str(SHT), 'sht:')
                if key not in self.skip_reasons:
                    self.skip_reasons[key] = 0
                self.skip_reasons[key] = self.skip_reasons[key] + 1
                self.skip(me.name)
                should_skip = True
            elif me.name in self.expected_failures:
                if VERBOSE:
                    print(f"Skipping {me.name} ({', '.join([self.URIname(t) for t in me.traits])})"
                          f" - {self.expected_failures[me.name]}")
                key = self.expected_failures[me.name]
                if key not in self.skip_reasons:
                    self.skip_reasons[key] = 0
                self.skip_reasons[key] = self.skip_reasons[key] + 1
                self.skip(me.name)
                should_skip = True
            if should_skip and not TEST_SKIPS_ONLY:
                return True
            if TEST_SKIPS_ONLY and not should_skip:
                return True

            # Validate the entry
            if VERBOSE:
                shex_uri = self.mfst.schema_loader.location_rewrite(me.schema_uri)
                data_uri = self.mfst.data_redirector.uri_for(me.data_uri) \
                    if self.mfst.data_redirector else me.data_uri
                print(f"Testing {me.name} ({'P' if me.should_pass else 'F'}): {shex_uri} - {data_uri}")
            g, s = me.data_graph(), me.shex_schema()
            if g is None and me.data_uri:
                print("\t ERROR: Unable to load data file")
                print(f"\t TRAITS: ({','.join(me.traits)})")
                self.skip(me.name)
                return True
            if not s:
                print(f"\t ERROR: Unable to load schema {me.schema_uri}")
                print(f"\t TRAITS: ({','.join(me.traits)})")
                self.nskipped += 1
                self.skip(me.name)
                return False

            cntxt = Context(g, s, me.extern_shape_for, base_namespace=BASE_FILE_LOC)
            cntxt.debug_context.debug = DEBUG
            map_ = FixedShapeMap()
            focus = self.mfst.data_uri(me.focus)
            if not focus:
                print("\t***** FAIL *****")
                print(f"\tFocus: {me.focus} not in schema")
                print(f"\t TRAITS: ({','.join(me.traits)})")
                self.fail(me.name)
                return False
            # if ':' not in focus:
            #     focus = "file://" + focus
            map_.add(ShapeAssociation(focus, ShExJ.IRIREF(me.shape) if me.shape else START))

            #################################
            #  Actual validation occurs here
            #################################
            rslt = isValid(cntxt, map_)

            test_result, reasons = rslt[0] or not me.should_pass, rslt[1]

            # Analyze the result
            if not VERBOSE and not test_result:
                print(f"Failed {me.name} ({'P' if me.should_pass else 'F'}): {me.schema_uri} - {me.data_uri}")
                print(f"\t TRAITS: ({','.join(me.traits)})")
            if test_result:
                self.pass_(me.name)
            else:
                if VERBOSE:
                    print("\t**** FAIL *****")
                    print(f"\t TRAITS: ({','.join(me.traits)})")
                    for reason in reasons:
                        print(f"\t{reason}")
                self.fail(me.name)
            return test_result

    def do_test(self, earl: Optional[EARLPage]=None):
        self.earl_report = earl
        if ENTRY_NAME:
            rslt = self.eval_entry(ENTRY_NAME)
        else:
            if CONTINUE_ON_FAIL:
                rslt = all([self.eval_entry(k) for k in self.mfst.entries.keys()])
            else:
                rslt = all(self.eval_entry(k) for k in self.mfst.entries.keys())

        print(f"\n{self.nfailed + self.npassed + self.nskipped} Tests\n\t{self.npassed} "
              f"Passed\n\t{self.nfailed} Failed\n\t{self.nskipped} Skips")

        from pprint import PrettyPrinter
        pp = PrettyPrinter().pprint
        pp(self.skip_reasons)
        self.assertTrue(rslt)
