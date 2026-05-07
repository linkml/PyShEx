import os
import re
from typing import cast, TextIO

from ShExJSG import ShExJ
from pyjsg.jsglib import loads
from pyshexc.parser_impl import generate_shexj
from pyshexc.parser_impl.generate_shexj import load_shex_file


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

    def load(self, schema_file: str | TextIO, schema_location: str | None = None) -> ShExJ.Schema:
        """ Load a ShEx Schema from schema_location

        :param schema_file:  name or file-like object to deserialize
        :param schema_location: URL or file name of schema.  Used to create the base_location
        :return: ShEx Schema represented by schema_location
        """
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
        return self.loads(self.schema_text)

    def loads(self, schema_txt: str) -> ShExJ.Schema:
        """ Parse and return schema as a ShExJ Schema

        :param schema_txt: ShExC or ShExJ representation of a ShEx Schema
        :return: ShEx Schema representation of schema
        """
        self.schema_text = schema_txt
        if schema_txt.strip()[0] == '{':
            # TODO: figure out how to propagate self.base_location into this parse
            return cast(ShExJ.Schema, loads(schema_txt, ShExJ))
        else:
            return generate_shexj.parse(schema_txt, self.base_location)

    def location_rewrite(self, schema_location: str) -> str:
        if self.root_location is not None and self.redirect_location is not None:
            rval = schema_location.replace(self.root_location, self.redirect_location) \
                if self.root_location and schema_location.startswith(self.root_location) else schema_location
        else:
            rval = schema_location
        if self.schema_format:
            rval = re.sub(r'\.[^.]+?(tern)?$',f'.{self.schema_format}\\1', rval)
        return rval
