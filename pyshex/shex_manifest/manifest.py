import os
from urllib.parse import urlsplit
from typing import cast

import requests
from ShExJSG.ShExJ import Schema
from jsonasobj import JsonObj, load
from rdflib import Graph

from pyshex.shex_evaluator import EvaluationResult, ShExEvaluator
from pyshex.utils.schema_loader import SchemaLoader


def fetch_uri(self, url: str, base: str="") -> str | None:
    req = requests.get(base + url)
    if req.ok:
        return req.text
    else:
        print(f"{base + url} {req.reason}" )
        return None


class ManifestEntry(JsonObj):
    schemaLabel: str
    schemaURL: str
    dataLabel: str
    dataURL : str
    queryMap: str
    status: str
    _manifest: "Manifest"

    _schema_text: str
    _schema: Schema
    _rdf_text: str
    _rdf: Graph

    def resolve(self) -> bool:
        """ Resolve the schema and data

        :return: success indicator
        """

    @property
    def schema_text(self) -> str:
        if getattr(self, '_schema_text') is None:
            self._schema_text = fetch_uri(self.schemaURL, self._manifest.base)
        return self._schema_text

    @property
    def schema(self) -> Schema:
        if getattr(self, '_schema') is None:
            self._schema = SchemaLoader().loads(self.schema_text)
        return self._schema

    @property
    def rdf_text(self, format_:str ="turtle") -> str:
        if getattr(self, '_rdf_text') is None:
            self._rdf_text = fetch_uri(self.dataURL, self._manifest.base)
        return self._rdf_text

    @property
    def rdf(self) -> Graph:
        if getattr(self, '_rdf') is None:
            self._rdf = Graph()
            # TODO - look at rdf-translator (https://bitbucket.org/alexstolz/rdf-translator) and Pygments to
            # guess the format
            self._rdf.parse(data=self.rdf_text, format="turtle")
        return self._rdf

    def evaluate(self, debug: bool | None = None, debug_slurps: bool | None = None,
                 over_slurp: bool | None = None) -> list[EvaluationResult]:
        return None



class Manifest:
    def __init__(self, source, base: str | None = None, debug: bool | None = False,
                 debug_slurps: bool | None = False,over_slurp: bool | None = True) -> None:
        """ Load a manifest

        :param source: file name, URI or file-like object that carries the manifest description
        :param base: RDF and ShEx base directory or URL.  If omitted, source file name/URI will be used
        :param debug: default debug setting for evaluate function
        :param debug_slurps: default debug_slurps setting for evaluate function
        :param over_slurp: default over_slurp setting for evaluate function
        """
        self.manifest = load(source)

        self.base = base
        if not self.base:
            if isinstance(source, str):
                if '://' in source:
                    self.base = urlsplit(source).path.split('/')[-1]
                else:
                    self.base = os.path.dirname(source)

        self.debug = debug
        self.debug_slurps = debug_slurps
        self.over_slurp = over_slurp
        for entry in self.manifest:
            entry._manifest = self

    @property
    def entries(self) -> list[ManifestEntry]:
        return cast(list[ManifestEntry], self.manifest)
