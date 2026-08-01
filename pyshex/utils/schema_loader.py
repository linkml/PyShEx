import os
import re
from pathlib import PureWindowsPath
from typing import cast, Optional, Set, TextIO
from urllib.parse import urljoin

from ShExJSG import ShExJ
from pyjsg.jsglib import loads
from pyshexc.parser_impl import generate_shexj
from pyshexc.parser_impl.generate_shexj import load_shex_file


# ShExJ members holding IRIs that are resolved against the document base.  Imports are
# deliberately excluded (resolve_imports handles them); bnode labels are never resolved.
_IRI_MEMBERS = {'id', 'predicate', 'datatype', 'start', 'valueExpr', 'inclusion',
                'extends', 'restricts', 'shapeExprs', 'expressions', 'values', 'shapeExpr',
                'expression'}


def _base_uri(loc: Optional[str]) -> Optional[str]:
    """ A Windows filesystem path is not a legal IRI (drive letter, backslashes):
    convert it to a file:/// URI before it is used as a document base.  POSIX paths
    are legal IRI references and are left untouched. """
    if loc and (re.match(r'^[A-Za-z]:[/\\]', loc) or loc.startswith('\\\\')):
        return PureWindowsPath(loc).as_uri()
    return loc


def _absolutize_shexj(node, base: str) -> None:
    """ Resolve relative IRIs in a parsed ShExJ document against base (jsg's JSON loader,
    unlike the ShExC parser, has no notion of a document base). """
    def fix(value, member):
        if isinstance(value, str):
            # only references/IRI-valued strings; leave bnode labels and absolute IRIs
            if member in _IRI_MEMBERS and not value.startswith('_:') and '://' not in value:
                return type(value)(urljoin(base, value))
            return value
        if isinstance(value, list):
            for i, item in enumerate(value):
                value[i] = fix(item, member)
            return value
        if hasattr(value, '_members') or hasattr(value, '__dict__'):
            for k in list(vars(value)):
                if k.startswith('_'):
                    continue
                v = getattr(value, k)
                if v is not None and k != 'imports':
                    # member context is the key itself: an ObjectLiteral's 'value' is
                    # lexical content, never an IRI, even inside a 'values' list
                    setattr(value, k, fix(v, k))
            return value
        return value

    fix(node, '')


class SchemaLoader:
    def __init__(self, base_location=None, redirect_location=None, schema_type_suffix=None) -> None:
        """ ShEx Schema loader, with the ability to redirect URI's to local directories or other URL's

        :param base_location: Location base supplied to `load` function
        :param redirect_location: Location to replace base for actual load
        :param schema_type_suffix: Replace schema file type suffix with this
        """
        self.base_location = base_location
        self.redirect_location = redirect_location
        self.schema_format = schema_type_suffix
        self.root_location = None
        self.schema_text = None
        self._source_base: Optional[str] = None

    def load(self, schema_file: str | TextIO, schema_location: str | None = None) -> ShExJ.Schema:
        """ Load a ShEx Schema from schema_location

        :param schema_file:  name or file-like object to deserialize
        :param schema_location: URL or file name of schema.  Used to create the base_location
        :return: ShEx Schema represented by schema_location
        """
        source = schema_file if isinstance(schema_file, str) else schema_location
        if isinstance(schema_file, str):
            schema_file = self.location_rewrite(schema_file)
            self.schema_text = load_shex_file(schema_file)
        else:
            self.schema_text = schema_file.read()

        if self.base_location:
            self.root_location = self.base_location
        elif schema_location:
            self.root_location = os.path.dirname(schema_location) + '/'
        else:
            self.root_location = None
        # Relative IRIs (including IMPORTs) resolve against the schema's canonical
        # location -- the original URL when a location redirect maps it to a local copy
        self._source_base = _base_uri(self.canonical_location(source))
        schema = self.loads(self.schema_text)
        return self.resolve_imports(schema, self._source_base)

    def loads(self, schema_txt: str) -> ShExJ.Schema:
        """ Parse and return schema as a ShExJ Schema

        :param schema_txt: ShExC or ShExJ representation of a ShEx Schema
        :return: ShEx Schema representation of schema
        """
        self.schema_text = schema_txt
        if schema_txt.strip()[0] == '{':
            schema = cast(ShExJ.Schema, loads(schema_txt, ShExJ))
            if self._source_base:
                _absolutize_shexj(schema, self._source_base)
            return schema
        else:
            return generate_shexj.parse(schema_txt, self._source_base or self.base_location)

    def canonical_location(self, schema_location: Optional[str]) -> Optional[str]:
        """ The canonical (usually remote) URL of a schema whose content may be loaded
        from a redirected local copy: the inverse of the redirect in location_rewrite. """
        if schema_location and self.base_location and self.redirect_location \
                and schema_location.startswith(self.redirect_location):
            return self.base_location + schema_location[len(self.redirect_location):]
        return schema_location

    def resolve_imports(self, schema: ShExJ.Schema, source: Optional[str],
                        visited: Optional[Set[str]] = None) -> ShExJ.Schema:
        """ Merge the shapes (and, if absent, the start declaration) of every schema in
        schema.imports, recursively, into schema.  Import IRIs are resolved against the
        importing schema's canonical location; an extensionless import is completed with
        '.shex' (which location_rewrite may map to another serialization). """
        if schema is None or not schema.imports:
            return schema
        if visited is None:
            visited = {source} if source else set()
        for imp in schema.imports:
            imp_url = urljoin(source or '', str(imp))
            if not re.search(r'\.[A-Za-z]+$', imp_url):
                imp_url += '.shex'
            if imp_url in visited:
                continue
            visited.add(imp_url)
            outer_text, outer_base = self.schema_text, self._source_base
            try:
                self._source_base = imp_url
                imported = self.loads(load_shex_file(self.location_rewrite(imp_url)))
                imported = self.resolve_imports(imported, imp_url, visited)
            finally:
                self.schema_text, self._source_base = outer_text, outer_base
            if imported.shapes:
                existing = {str(sh.id) for sh in (schema.shapes or []) if getattr(sh, 'id', None) is not None}
                for sh in imported.shapes:
                    if str(getattr(sh, 'id', None)) not in existing:
                        if schema.shapes is None:
                            schema.shapes = [sh]
                        else:
                            schema.shapes.append(sh)
            if schema.start is None and imported.start is not None:
                schema.start = imported.start
        # the imports are now folded into the schema; leave nothing for downstream
        # processors (eg Context's shape_importer hook) to re-resolve
        schema.imports = None
        return schema

    def location_rewrite(self, schema_location: str) -> str:
        if self.root_location is not None and self.redirect_location is not None:
            rval = schema_location.replace(self.root_location, self.redirect_location) \
                if self.root_location and schema_location.startswith(self.root_location) else schema_location
        else:
            rval = schema_location
        if self.schema_format:
            rval = re.sub(r'\.[^.]+?(tern)?$',f'.{self.schema_format}\\1', rval)
        return rval
