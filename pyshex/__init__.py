import rdflib

# A validator must see literals as written: rdflib's default lexical normalization
# rewrites e.g. "TRUE"^^xsd:boolean to "true" and "1E0"^^xsd:decimal to "1" at parse
# time, which would hide invalid lexical forms from datatype validation.
rdflib.NORMALIZE_LITERALS = False

# ... and the N3/Turtle tokenizer separately erases the lexical form of bare numerics
# (00 -> "0"^^xsd:integer)
from pyshex.utils.rdflib_lexical_fidelity import install as _install_lexical_fidelity
_install_lexical_fidelity()

from pyshex.prefixlib import PrefixLibrary, standard_prefixes, known_prefixes
from pyshex.shex_evaluator import ShExEvaluator

import rdflib_shim
shim_installed = rdflib_shim.RDFLIB_SHIM
