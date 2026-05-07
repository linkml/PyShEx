import os
import sys

import pytest
from ShExJSG import ShExJ
from pyjsg.jsglib import load
from rdflib import URIRef, Namespace, Graph

from tests.utils.manifest import ShExManifest

data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
validation_dir = os.path.join(data_dir, 'validation')
schemas_dir = os.path.join(data_dir, 'schemas')
manifest_ttl = os.path.join(validation_dir, 'manifest.ttl')
manifest_json = os.path.join(validation_dir, 'manifest.jsonld')

SHEX = Namespace("http://www.w3.org/ns/shex#")
MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
SHT = Namespace("http://www.w3.org/ns/shacl/test-suite#")
SX = Namespace("https://shexspec.github.io/shexTest/ns#")

entries_list = {
    '0_empty',
    '0_other',
    '0_otherbnode',
    '1Adot_pass',
    '1dot-base_fail-empty',
    '1dot-base_fail-missing',
    '1dot-base_pass-noOthers',
    '1dotLNdefault_pass-noOthers',
    '1dotLNex-HYPHEN_MINUS_pass-noOthers',
    '1dotNS2_pass-noOthers',
    '1dotNSdefault_pass-noOthers',
    '1dotSemi_pass-noOthers',
    '1dot_fail-empty',
    '1dot_fail-missing',
    '1dot_pass-noOthers',
    '1dot_pass-others_lexicallyEarlier',
    '1dot_pass-others_lexicallyLater',
    '1inversedot_fail-empty',
    '1inversedot_fail-missing',
    '1inversedot_pass-noOthers',
    '1inversedot_pass-over_lexicallyEarlier',
    '1inversedot_pass-over_lexicallyLater',
    'bnode1dot_fail-missing',
    'bnode1dot_pass-others_lexicallyEarlier',
    'PstarT',
}

# TODO: Remove this once the rdflib list recursion issue is resolved
sys.setrecursionlimit(1200)


def test_basics_ttl():
    mfst = ShExManifest(manifest_ttl, 'turtle')
    assert entries_list == set(mfst.entries.keys()).intersection(entries_list)


def test_basics_jsonld():
    mfst = ShExManifest(manifest_json)
    assert entries_list == set(mfst.entries.keys()).intersection(entries_list)


def attributes_tester(mfst: ShExManifest) -> None:
    me = mfst.entries['1dotSemi_pass-noOthers']
    assert len(me) == 1
    me = me[0]
    assert me.name == '1dotSemi_pass-noOthers'
    assert me.traits == {SHT.TriplePattern}
    assert me.comments == 'PREFIX : <http://a.example/> <S1> { :p1 ., } on { <s1> <p1> <o1> }'
    assert me.status == MF.proposed
    assert me.entry_type == SHT.ValidationTest
    assert me.should_parse
    assert me.should_pass
    assert me.schema_uri == URIRef('https://raw.githubusercontent.com/shexSpec/shexTest/master/schemas/1dotSemi.shex')
    assert me.shape == URIRef("http://a.example/S1")
    assert me.data_uri == URIRef('https://raw.githubusercontent.com/shexSpec/shexTest/master/validation/Is1_Ip1_Io1.ttl')
    assert me.focus == URIRef("http://a.example/s1")

    me = mfst.entries['bnode1dot_pass-others_lexicallyEarlier'][0]
    assert me.traits == {SHT.BNodeShapeLabel, SHT.TriplePattern}

    me = mfst.entries['1inversedot_fail-empty'][0]
    assert me.traits == {SHT.TriplePattern}
    assert me.should_parse
    assert not me.should_pass
    assert me.status == MF.proposed
    assert me.comments == "<S> { ^<p1> . } on {  }"


def test_attributes_ttl():
    mfst = ShExManifest(manifest_ttl, manifest_format="turtle")
    attributes_tester(mfst)


@pytest.mark.skip(reason="Issue report #27 filed in shexTest")
def test_attributes_jsonld():
    mfst = ShExManifest(manifest_json)
    attributes_tester(mfst)


def test_shex():
    mfst = ShExManifest(manifest_ttl, "turtle")
    me = mfst.entries['1Adot_pass'][0]
    assert me.schema_uri == URIRef('https://raw.githubusercontent.com/shexSpec/shexTest/master/schemas/1Adot.shex')
    with open(os.path.join(schemas_dir, '1Adot.json')) as shex_file:
        target_shex_file = load(shex_file, ShExJ)
        del target_shex_file['@context']
        assert target_shex_file._as_json == mfst.entries['1Adot_pass'][0].shex_schema()._as_json


def test_data():
    mfst = ShExManifest(manifest_ttl, 'turtle')
    me = mfst.entries['PstarT'][0]
    g = Graph()
    g.parse(os.path.join(validation_dir, 'Pstar.ttl'), format="turtle")
    assert set(g) == set(me.data_graph(fmt="turtle"))


def test_full_ttl():
    mfst = ShExManifest(manifest_ttl, 'turtle')
    assert entries_list == entries_list.intersection(mfst.entries)


def test_full_json():
    mfst = ShExManifest(manifest_json)
    assert entries_list == entries_list.intersection(mfst.entries)


def test_externs():
    mfst = ShExManifest(manifest_ttl, 'turtle')
    me = mfst.entries['shapeExtern_pass'][0]
    assert me.externs == [URIRef('https://raw.githubusercontent.com/shexSpec/shexTest/master/schemas/shapeExtern.shextern')]
    me = mfst.entries['1Adot_pass'][0]
    assert me.externs == []


def test_extern_str():
    mfst = ShExManifest(manifest_ttl, 'turtle')
    me = mfst.entries['shapeExtern_pass'][0]
    assert me.extern_shape_for(ShExJ.IRIREF("http://a.example/Sext")) is not None