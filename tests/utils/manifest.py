import json
import json
from typing import List, Dict, Set, Union, Optional, Tuple

import os
from ShExJSG import ShExJ
from rdflib import Graph, ConjunctiveGraph, RDF, RDFS, URIRef, Namespace, Literal, BNode
from urllib.request import urlopen

from rdflib.collection import Collection

from pyshex.shape_expressions_language.p5_context import Context
from pyshex.utils.schema_loader import SchemaLoader

# The LexicalBNode / ToldBNode / BNodeShapeLabel tests address blank nodes in the data by
# the labels used in the source document.  rdflib's turtle parser generates fresh ids for
# labeled bnodes; patch the (test-local) parser to preserve them so the manifest's
# sht:focus _:xyz can be correlated with the parsed data.
from rdflib import BNode as _BNode
from rdflib.plugins.parsers import notation3 as _notation3


def _preserving_anonymous_node(self, ln):
    term = self._anonymousNodes.get(ln, None)
    if term is None:
        term = _BNode(ln)
        self._anonymousNodes[ln] = term
    return term


_notation3.SinkParser.anonymousNode = _preserving_anonymous_node
from pyshex.utils.url_utils import generate_base
from tests.utils.uri_redirector import URIRedirector

SHT = Namespace("http://www.w3.org/ns/shacl/test-suite#")
MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")


class ShExManifestEntry:
    def __init__(self, entryuri: URIRef, g: Graph, owner: "ShExManifest") -> None:
        """ An individual manifest entry

        :param entryuri: URI of the entry
        :param g: graph containing the entry
        """
        self.g = g
        self.entryuri = entryuri
        self.owner = owner
        # Action appears to have been removed.  If it isn't present, we pull what we need from the root
        action = self.g.value(self.entryuri, MF.action, any=False)
        assert action, f"{self.entryuri} : Invalid action list in entry"
        self.action_ = {p: o for p, o in g.predicate_objects(action)}
        assert self.action_, "No actions"

    def _action_obj(self, p) -> Union[URIRef, Literal]:
        return self.action_.get(p)

    @property
    def name(self) -> str:
        return str(self.g.value(self.entryuri, MF.name, any=False))

    @property
    def traits(self) -> Set[URIRef]:
        return set(self.g.objects(self.entryuri, SHT.trait))

    @property
    def comments(self) -> str:
        return '\n'.join([str(e) for e in self.g.objects(self.entryuri, RDFS.comment)])

    @property
    def status(self) -> URIRef:
        return self.g.value(self.entryuri, MF.status, any=False)

    @property
    def entry_type(self) -> URIRef:
        """ Possible types are:
        SHT.NegativeStructure
        SHT.NegativeSyntax
        SHT.RepresentationTest
        SHT.ValidationFailure
        SHT.ValidationTest
        """
        return self.g.value(self.entryuri, RDF.type, any=False)

    @property
    def should_parse(self) -> bool:
        return self.entry_type != SHT.NegativeSyntax

    @property
    def should_pass(self) -> bool:
        return self.entry_type == SHT.ValidationTest

    @property
    def schema_uri(self) -> Optional[URIRef]:
        return self._action_obj(SHT.schema)

    def shex_schema(self) -> Optional[ShExJ.Schema]:
        redirected_uri = self.owner.schema_uri(self.schema_uri)
        return self.owner.schema_loader.load(redirected_uri, redirected_uri)

    @property
    def shape(self) -> Optional[URIRef]:
        return self._action_obj(SHT.shape)

    @property
    def data_uri(self) -> Optional[URIRef]:
        return self._action_obj(SHT.data)

    def data(self) -> Optional[str]:
        if self.data_uri:
            uri = self.owner.data_uri(self.data_uri)
            if '://' in str(uri):
                return urlopen(str(uri)).read().decode()
            else:
                with open(uri, 'rb') as data_file:
                    return data_file.read().decode()
        return None

    @property
    def focus(self) -> Optional[URIRef]:
        return self._action_obj(SHT.focus)

    @property
    def map_uri(self) -> Optional[URIRef]:
        return self._action_obj(SHT.map)

    def shape_map(self) -> Optional[List[Tuple[str, str]]]:
        """ (node, shape) pairs from the sht:map JSON file, if present """
        if self.map_uri is None:
            return None
        uri = str(self.owner.data_uri(self.map_uri))
        if '://' in uri and not uri.startswith('file://'):
            import urllib.request
            with urllib.request.urlopen(uri) as f:
                entries = json.load(f)
        else:
            with open(uri.replace('file://', '')) as f:
                entries = json.load(f)
        return [(e['node'], e['shape']) for e in entries]

    def data_graph(self, fmt="turtle") -> Optional[Graph]:
        g = Graph()
        # parse against the canonical (remote) location so relative IRIs in the data
        # land in the same IRI space as the schema's
        base_uri = str(self.owner.data_uri(self.data_uri))
        canonical = self.owner.schema_loader.canonical_location(base_uri.replace('file://', ''))
        base = generate_base(canonical if canonical else base_uri)
        data_ttl = f"@base <{base}> .\n {self.data()}"
        g.parse(data=data_ttl, format=fmt)
        return g

    @property
    def externs(self) -> List[URIRef]:
        externs = self._action_obj(SHT.shapeExterns)
        return [] if externs is None else [e for e in Collection(self.g, externs)] \
            if isinstance(externs, BNode) else [externs]

    def extern_shape_for(self, ref: ShExJ.IRIREF) -> Optional[ShExJ.Shape]:
        for extern in self.externs:
            extern_schema = self.owner.schema_loader.load(extern)
            if extern_schema:
                cntxt = Context(None, extern_schema)
                if ref in cntxt.schema_id_map:
                    return cntxt.schema_id_map[ref]
        return None

    def __str__(self):
        return str(self.name)


class ShExManifest:
    def __init__(self, file_loc: str, manifest_format: str='json-ld', shex_format=None) -> None:
        """
        A ShEx Manifest traversal tool

        :param file_loc: Location of the manifest file
        :param manifest_format: Format of the manifest file (e.g. 'turtle', 'json-ld')
        :param shex_format: Format of the ShEx files in the manifest. If None, use what the manifest says, otherwise
        replace '.shex' with shex_format
        """
        self.g = ConjunctiveGraph()
        self.g.parse(file_loc, format=manifest_format)
        self.entries: Dict[str, List[ShExManifestEntry]] = {}
        self.schema_loader = SchemaLoader()
        self.data_redirector: Optional[URIRedirector] = None
        self.schema_redirector: Optional[URIRedirector] = None

        manifest = self.g.value(None, RDF.type, MF.Manifest, any=False)
        for e in Collection(self.g, self.g.value(manifest, MF.entries, any=False)):
            entry = ShExManifestEntry(e, self.g, self)
            self.entries.setdefault(str(entry), []).append(entry)

    def data_uri(self, uri: URIRef) -> Union[URIRef, str]:
        return self.data_redirector.uri_for(uri) if self.data_redirector else uri

    def schema_uri(self, uri: URIRef) -> Union[URIRef, str]:
        return self.schema_redirector.uri_for(uri) if self.schema_redirector else uri
