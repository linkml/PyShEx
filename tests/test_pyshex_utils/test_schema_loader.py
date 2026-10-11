import codecs
import os

from rdflib import RDF

from pyshex.utils.schema_loader import SchemaLoader, load_shex_file


SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'schemas'))

SHEXC_INLINE = """<http://a.example/S1> {
   ( <http://a.example/p1> .|
     <http://a.example/p2> .|
     <http://a.example/p3> .|
     <http://a.example/p4> .
   ){2,3}
}"""

SHEXJ_INLINE = """{
  "@context": "http://www.w3.org/ns/shex.jsonld",
  "type": "Schema",
  "shapes": [
    {
      "id": "http://a.example/S1",
      "type": "Shape",
      "expression": {
        "type": "TripleConstraint",
        "predicate": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
      }
    }
  ]
}"""

EXPECTED_SHAPE_ID = "http://a.example/S1"
SHEXC_URL = "https://raw.githubusercontent.com/shexSpec/shexTest/2.0/schemas/startCode3.shex"
SHEXJ_URL = "https://raw.githubusercontent.com/shexSpec/shexTest/2.0/schemas/startCode3.json"


def test_loads_shexc() -> None:
    """Load a ShExC string and verify shape id and predicates."""
    schema = SchemaLoader().loads(SHEXC_INLINE)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID
    assert {e.predicate for e in schema.shapes[0].expression.expressions} == {
        "http://a.example/p1",
        "http://a.example/p2",
        "http://a.example/p3",
        "http://a.example/p4",
    }


def test_loads_shexj() -> None:
    """Load a ShExJ string and verify shape id and predicate."""
    schema = SchemaLoader().loads(SHEXJ_INLINE)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID
    assert schema.shapes[0].expression.predicate == str(RDF.type)


def test_load_shexc_from_file_and_url() -> None:
    loader = SchemaLoader()
    fileloc = os.path.join(SCHEMAS_DIR, 'startCode3.shex')

    schema = loader.load(fileloc)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID

    with open(fileloc) as f:
        schema = loader.load(f)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID

    schema = loader.load(SHEXC_URL)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID


def test_load_shexj_from_file_and_url() -> None:
    loader = SchemaLoader()
    fileloc = os.path.join(SCHEMAS_DIR, 'startCode3.json')

    schema = loader.load(fileloc)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID

    with open(fileloc) as f:
        schema = loader.load(f)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID

    schema = loader.load(SHEXJ_URL)
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID


def test_location_rewrite() -> None:
    loader = SchemaLoader()
    loader.root_location = "https://raw.githubusercontent.com/shexSpec/shexTest/2.0/schemasz/"
    loader.redirect_location = SCHEMAS_DIR + '/'
    schema = loader.load(loader.root_location + 'startCode3.shex')
    assert schema.shapes[0].id == EXPECTED_SHAPE_ID


def test_format_change() -> None:
    loc = "https://raw.githubusercontent.com/shexSpec/shexTest/2.0/schemas/startCode3"
    loader = SchemaLoader(schema_type_suffix='json')
    assert loader.location_rewrite(f"{loc}.shex") == f"{loc}.json"
    assert loader.location_rewrite(f"{loc}.shextern") == f"{loc}.jsontern"
    loader.schema_format = 'shex'
    assert loader.location_rewrite(f"{loc}.shex") == f"{loc}.shex"
    assert loader.location_rewrite(f"{loc}.shextern") == f"{loc}.shextern"
    assert loader.location_rewrite(f"{loc}.jsontern") == f"{loc}.shextern"


# A UTF-8 character after ~300KB of ASCII: chardet only samples the start and reports
# ascii with confidence 1.0 (as it does for FHIR R4's fhir.shex), which used to crash decode()
CAFE_SHEXC = '<http://a.example/S1> { <http://a.example/p1> ["caf\u00e9"] }\n'


def test_load_shexc_utf8_after_long_ascii_prefix(tmp_path) -> None:
    shex_file = tmp_path / 'long.shex'
    shex_file.write_bytes(('# padding line for chardet\n' * 12000 + CAFE_SHEXC).encode('utf-8'))
    assert load_shex_file(str(shex_file)).endswith(CAFE_SHEXC)
    schema = SchemaLoader().load(str(shex_file))
    assert schema.shapes[0].expression.valueExpr.values[0].value == 'caf\u00e9'


def test_load_shexc_non_utf8_falls_back(tmp_path) -> None:
    """ShExC must be UTF-8, but a Latin-1 file still loads rather than crashing.
    Which 8-bit encoding chardet guesses for so short a sample varies, so only the ASCII is checked."""
    shex_file = tmp_path / 'latin1.shex'
    shex_file.write_bytes(CAFE_SHEXC.encode('latin-1'))
    text = load_shex_file(str(shex_file))
    assert len(text) == len(CAFE_SHEXC)
    e_acute = CAFE_SHEXC.index('é')
    assert text[:e_acute] + 'é' + text[e_acute + 1:] == CAFE_SHEXC


def test_load_shexc_utf8_bom(tmp_path) -> None:
    shex_file = tmp_path / 'bom.shex'
    shex_file.write_bytes(codecs.BOM_UTF8 + CAFE_SHEXC.encode('utf-8'))
    assert load_shex_file(str(shex_file)) == CAFE_SHEXC
