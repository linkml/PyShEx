import re

from pyshexc.parser_impl.generate_shexj import load_shex_file
from rdflib import Namespace, Graph, RDF, RDFS, XSD, URIRef, __version__
from rdflib.namespace import DOAP, FOAF, DC, DCTERMS, SKOS, OWL, XMLNS
if __version__.startswith("5."):
    from rdflib.namespace import _RDFNamespace
    BuiltinNamespace = _RDFNamespace
else:
    from rdflib.namespace import DefinedNamespaceMeta
    BuiltinNamespace = DefinedNamespaceMeta


from pyshex.utils.deprecated import deprecated


class PrefixLibrary:
    unique_token = object()

    def __init__(self, schema: str | None = None, **kwlibs: str | Namespace) -> None:
        """ Generate a prefix library from a ShEx schema

        :param schema: ShExC Schema
        :param kwlibs: Additional key/value pairs
        """
        if schema is not None:
            self.add_shex(schema)

        for k, v in kwlibs.items():
            self[k] = v

    def __iter__(self):
        for k, v in self.__dict__.items():
            if isinstance(v, Namespace):
                yield (k, v)

    def __str__(self) -> str:
        """ Return the ShEx representation of the library """
        rval = ""
        for k, v in self:
            rval += f"PREFIX {k.lower()}: <{str(v)}>\n"
        return rval + '\n'

    def __setitem__(self, key, value):
        setattr(self, key.upper(), value if isinstance(value, Namespace) else Namespace(value))

    def add_shex(self, schema: str) -> "PrefixLibrary":
        """ Add a ShExC schema to the library

        :param schema: ShExC schema text, URL or file name
        :return: prefix library object
        """
        if '\n' in schema or '\r' in schema or ' ' in schema:
            shex = schema
        else:
            shex = load_shex_file(schema)

        for line in shex.split('\n'):
            line = line.strip()
            m = re.match(r'PREFIX\s+(\S+):\s+<(\S+)>', line)
            if not m:
                m = re.match(r"@prefix\s+(\S+):\s+<(\S+)>\s+\.", line)
            if m:
                setattr(self, m.group(1).upper(), Namespace(m.group(2)))
        return self

    def add_rdf(self, rdf: str | Graph, format: str | None = "turtle") -> "PrefixLibrary":
        if not isinstance(rdf, Graph):
            g = Graph()
            if '\n' in rdf or '\r' in rdf or ' ' in rdf:
                g.parse(data=rdf, format=format)
            else:
                g.parse(rdf, format=format)
        else:
            g = rdf
        for k, v in g.namespace_manager.namespaces():
            setattr(self, k.upper(), Namespace(v))
        return self

    def add_bindings_to(self, g: Graph) -> "PrefixLibrary":
        """ Add bindings in the library to the graph

        :param g: graph to add prefixes to
        :return: PrefixLibrary object
        """
        for prefix, namespace in self:
            g.bind(prefix.lower(), namespace)
        return self

    @deprecated
    def add_bindings(self, g: Graph) -> "PrefixLibrary":
        """ deprecated. Use: add_bindings_to """
        return self.add_bindings_to(g)

    def add_to_object(self, target: object, override: bool = False) -> int:
        """
         Add the bindings to the target object
        :param target: target to add to
        :param override: override existing bindings if they are of type Namespace
        :return: number of items actually added
        """
        nret = 0
        for k, v in self:
            key = k.upper()
            exists = hasattr(target, key)
            if not exists or (override and isinstance(getattr(target, k), (Namespace, BuiltinNamespace))):
                setattr(target, k, v)
                nret += 1
            else:
                print(f"Warning: {key} is already defined in namespace {target}. Not overridden")
        return nret

    def nsname(self, uri: str | URIRef) -> str:
        """
        Return the 'ns:name' format of URI

        :param uri: URI to transform
        :return: nsname format of URI or straight URI if no mapping
        """
        uri = str(uri)
        nsuri = ""
        prefix = None
        for pfx, ns in self:
            nss = str(ns)
            if uri.startswith(nss) and len(nss) > len(nsuri):
                nsuri = nss
                prefix = pfx
        return (prefix.lower() + ':' + uri[len(nsuri):]) if prefix is not None else uri


standard_prefixes = PrefixLibrary(None, rdf=RDF, rdfs=RDFS, xml=XMLNS, xsd=XSD)


known_prefixes = PrefixLibrary(None, dc=DC, dcterms=DCTERMS, doap=DOAP, foaf=FOAF, owl=OWL, rdf=RDF, rdfs=RDFS,
                               skos=SKOS, xsd=XSD, xmlns=XMLNS)
