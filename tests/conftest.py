import pytest
import os

BIOLINK_DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "test_biolink", "data")
BIOLINK_META_RDF_PATH = os.path.join(BIOLINK_DATA_DIR, "meta.ttl")
BIOLINK_META_SHEX_PATH = os.path.join(BIOLINK_DATA_DIR, "meta.json")
BIOLINK_NEW_META_SHEX_PATH = os.path.join(BIOLINK_DATA_DIR, "metashex.json")


@pytest.fixture
def biolink_meta_rdf() -> str:
    with open(BIOLINK_META_RDF_PATH) as f:
        return f.read()