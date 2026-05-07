""" Implementation of `5.4 <http://shex.io/shex-semantics/#node-constraints>`_"""

import numbers

from ShExJSG import ShExJ
from pyjsg.jsglib import isinstance_
from rdflib import URIRef, BNode, Literal, XSD, RDF
from jsonasobj import as_json

from pyshex.shape_expressions_language.p5_context import Context, DebugContext
from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import Node
from pyshex.sparql11_query.p17_1_operand_data_types import is_sparql_operand_datatype, is_numeric
from pyshex.utils.datatype_utils import can_cast_to, total_digits, fraction_digits, pattern_match, map_object_literal
from pyshex.utils.trace_utils import trace_satisfies
from pyshex.utils.value_set_utils import objectValueMatches, uriref_startswith_iriref, uriref_matches_iriref


@trace_satisfies()
def satisfiesNodeConstraint(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, _: DebugContext) -> bool:
    """ `5.4.1 Semantics <http://shex.io/shex-semantics/#node-constraint-semantics>`_

    For a node n and constraint nc, satisfies2(n, nc) if and only if for every nodeKind, datatype, xsFacet and
    values constraint value v present in nc nodeSatisfies(n, v). The following sections define nodeSatisfies for
    each of these types of constraints:
    """
    return nodeSatisfiesNodeKind(cntxt, n, nc) and nodeSatisfiesDataType(cntxt, n, nc) and \
        nodeSatisfiesStringFacet(cntxt, n, nc) and nodeSatisfiesNumericFacet(cntxt, n, nc) and \
        nodeSatisfiesValues(cntxt, n, nc)


@trace_satisfies(newline=False, skip_trace=lambda nc: nc.nodeKind is None)
def nodeSatisfiesNodeKind(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, c: DebugContext) -> bool:
    """ `5.4.2 Node Kind Constraints <http://shex.io/shex-semantics/#nodeKind>`_

    For a node n and constraint value v, nodeSatisfies(n, v) if:

        * v = "iri" and n is an IRI.
        * v = "bnode" and n is a blank node.
        * v = "literal" and n is a Literal.
        * v = "nonliteral" and n is an IRI or blank node.
    """
    if c.debug and nc.nodeKind is not None:
        print(f" Kind: {nc.nodeKind}")
    if nc.nodeKind is None or \
        (nc.nodeKind == 'iri' and isinstance(n, URIRef)) or \
        (nc.nodeKind == 'bnode' and isinstance(n, BNode)) or \
        (nc.nodeKind == 'literal' and isinstance(n, Literal)) or \
        (nc.nodeKind == 'nonliteral' and isinstance(n, (URIRef, BNode))):
        return True
    cntxt.fail_reason = f"Node kind mismatch have: {type(n).__name__} expected: {nc.nodeKind}"
    return False


@trace_satisfies(newline=False, skip_trace=lambda nc: nc.datatype is None)
def nodeSatisfiesDataType(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, c: DebugContext) -> bool:
    """ `5.4.3 Datatype Constraints <http://shex.io/shex-semantics/#datatype>`_

    For a node n and constraint value v, nodeSatisfies(n, v) if n is an Literal with the datatype v and, if v is in
    the set of SPARQL operand data types[sparql11-query], an XML schema string with a value of the lexical form of
    n can be cast to the target type v per XPath Functions 3.1 section 19 Casting[xpath-functions]. Only datatypes
    supported by SPARQL MUST be tested but ShEx extensions MAY add support for other datatypes.
    """
    if nc.datatype is None:
        return True
    if c.debug:
        print(f" Datatype: {nc.datatype}")
    if not isinstance(n, Literal):
        cntxt.fail_reason = f"Datatype constraint ({nc.datatype}) " \
            f"does not match {type(n).__name__} {cntxt.n3_mapper.n3(n)}"
        cntxt.dump_bnode(n)
        return False
    actual_datatype = _datatype(n)
    if actual_datatype == str(nc.datatype) or \
        (is_sparql_operand_datatype(nc.datatype) and can_cast_to(n, nc.datatype)):
        return True
    cntxt.fail_reason = f"Datatype mismatch - expected: {nc.datatype} actual: {actual_datatype}"
    return False


def _datatype(n: Literal) -> str:
    return str(RDF.langString) if (n.datatype is None or n.datatype == XSD.string) and n.language else \
        str(XSD.string) if n.datatype is None else \
        str(n.datatype)


@trace_satisfies(skip_trace=lambda nc: nc.length is None and nc.minlength is None and
                                       nc.maxlength is None and nc.pattern is None)
def nodeSatisfiesStringFacet(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, _c: DebugContext) -> bool:
    """ `5.4.5 XML Schema String Facet Constraints <ttp://shex.io/shex-semantics/#xs-string>`_

     String facet constraints apply to the lexical form of the RDF Literals and IRIs and blank node
     identifiers (see note below regarding access to blank node identifiers).
    """

    # Let lex =
    #
    #  * if the value n is an RDF Literal, the lexical form of the literal (see[rdf11-concepts] section 3.3 Literals).
    #  * if the value n is an IRI, the IRI string (see[rdf11-concepts] section 3.2 IRIs).
    #  * if the value n is a blank node, the blank node identifier (see[rdf11-concepts] section 3.4 Blank Nodes).
    if nc.length is not None or nc.minlength is not None or nc.maxlength is not None \
            or nc.pattern is not None:
        lex = str(n)
        #  Let len = the number of unicode codepoints in lex
        # For a node n and constraint value v, nodeSatisfies(n, v):
        #
        #  * for "length" constraints, v = len,
        #  * for "minlength" constraints, v >= len,
        #  * for "maxlength" constraints, v <= len,
        #  * for "pattern" constraints, v is unescaped into a valid XPath 3.1 regular expression[xpath-functions-31]
        #    re and invoking fn:matches(lex, re) returns fn:true. If the flags parameter is present, it is passed
        #    as a third argument to fn:matches. The pattern may have XPath 3.1 regular expression escape sequences
        #    per the modified production [10] in section 5.6.1.1 as well as numeric escape sequences of the
        #    form 'u' HEX HEX HEX HEX or 'U' HEX HEX HEX HEX HEX HEX HEX HEX. Unescaping replaces numeric escape
        #    sequences with the corresponding unicode codepoint

        # TODO: Figure out whether we need to connect this to the lxml exslt functions
        # TODO: Map flags if not
        if (nc.length is None or len(lex) == nc.length) and \
           (nc.minlength is None or len(lex) >= nc.minlength) and \
           (nc.maxlength is None or len(lex) <= nc.maxlength) and \
           (nc.pattern is None or pattern_match(nc.pattern, nc.flags, lex)):
            return True
        elif nc.length is not None and len(lex) != nc.length:
            cntxt.fail_reason = f"String length mismatch - expected: {nc.length} actual: {len(lex)}"
        elif nc.minlength is not None and len(lex) < nc.minlength:
            cntxt.fail_reason = f"String length violation - minimum: {nc.minlength} actual: {len(lex)}"
        elif nc.maxlength is not None and len(lex) > nc.maxlength:
            cntxt.fail_reason = f"String length violation - maximum: {nc.maxlength} actual: {len(lex)}"
        elif nc.pattern is not None and not pattern_match(nc.pattern, nc.flags, lex):
            cntxt.fail_reason = f"Pattern match failure - pattern: {nc.pattern} flags:{nc.flags}" \
                                             f" string: {lex}"
        else:
            cntxt.fail_reason = "Programming error - flame the programmer"
        return False


    else:
        return True


@trace_satisfies(newline=True, skip_trace=lambda nc: nc.mininclusive is None and nc.minexclusive is None and
                                                 nc.maxinclusive is None and nc.maxexclusive is None and
                                                 nc.totaldigits is None and nc.fractiondigits is None)
def nodeSatisfiesNumericFacet(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, _c: DebugContext) -> bool:
    """ `5.4.5 XML Schema Numeric Facet Constraints <http://shex.io/shex-semantics/#xs-numeric>`_

    Numeric facet constraints apply to the numeric value of RDF Literals with datatypes listed in SPARQL 1.1
    Operand Data Types[sparql11-query]. Numeric constraints on non-numeric values fail. totaldigits and
    fractiondigits constraints on values not derived from xsd:decimal fail.
    """
    if nc.mininclusive is not None or nc.minexclusive is not None or nc.maxinclusive is not None \
            or nc.maxexclusive is not None or nc.totaldigits is not None or nc.fractiondigits is not None:
        if is_numeric(n):
            v = n.value
            if isinstance(v, numbers.Number):
                if (nc.mininclusive is None or v >= nc.mininclusive) and \
                   (nc.minexclusive is None or v > nc.minexclusive) and \
                   (nc.maxinclusive is None or v <= nc.maxinclusive) and \
                   (nc.maxexclusive is None or v < nc.maxexclusive) and \
                   (nc.totaldigits is None or (total_digits(n) is not None and
                                                   total_digits(n) <= nc.totaldigits)) and \
                   (nc.fractiondigits is None or (fraction_digits(n) is not None and
                                                      fraction_digits(n) <= nc.fractiondigits)):
                    return True
                else:
                    if nc.mininclusive is not None and v < nc.mininclusive:
                        cntxt.fail_reason = f"Numeric value volation - minimum inclusive: " \
                                                         f"{nc.mininclusive} actual: {v}"
                    elif nc.minexclusive is not None and v <= nc.minexclusive:
                        cntxt.fail_reason = f"Numeric value volation - minimum exclusive: " \
                                                         f"{nc.minexclusive} actual: {v}"
                    elif nc.maxinclusive is not None and v > nc.maxinclusive:
                        cntxt.fail_reason = f"Numeric value volation - maximum inclusive: " \
                                                         f"{nc.maxinclusive} actual: {v}"
                    elif nc.maxexclusive is not None and v >= nc.maxexclusive:
                        cntxt.fail_reason = f"Numeric value volation - maximum exclusive: " \
                                                         f"{nc.maxexclusive} actual: {v}"
                    elif nc.totaldigits is not None and (total_digits(n) is None or
                                                             total_digits(n) > nc.totaldigits):
                        cntxt.fail_reason = f"Numeric value volation - max total digits: " \
                                                         f"{nc.totaldigits} value: {v}"
                    elif nc.fractiondigits is not None and (fraction_digits(n) is None or
                                                                total_digits(n) > nc.fractiondigits):
                        cntxt.fail_reason = f"Numeric value volation - max fractional digits: " \
                                                         f"{nc.fractiondigits} value: {v}"
                    else:
                        cntxt.fail_reason = "Impossible error - kick the programmer"
                    return False
            else:
                cntxt.fail_reason = "Numeric test on non-number: {v}"
                return False
        else:
            cntxt.fail_reason = "Numeric test on non-number: {n}"
            return False
    return True


@trace_satisfies(skip_trace=lambda nc: nc.values is None)
def nodeSatisfiesValues(cntxt: Context, n: Node, nc: ShExJ.NodeConstraint, _c: DebugContext) -> bool:
    """ `5.4.5 Values Constraint <http://shex.io/shex-semantics/#values>`_

     For a node n and constraint value v, nodeSatisfies(n, v) if n matches some valueSetValue vsv in v.
    """
    if nc.values is None:
        return True
    else:
        if any(_nodeSatisfiesValue(cntxt, n, vsv) for vsv in nc.values):
            return True
        else:
            cntxt.fail_reason = f"Node: {cntxt.n3_mapper.n3(n)} not in value set:\n\t " \
                f"{as_json(cntxt.type_last(nc), indent=None)[:60]}..."
            return False


def _nodeSatisfiesValue(cntxt: Context, n: Node, vsv: ShExJ.valueSetValue) -> bool:
    """
    A term matches a valueSetValue if:
        * vsv is an objectValue and n = vsv.
        * vsv is a Language with langTag lt and n is a language-tagged string with a language tag l and l = lt.
        * vsv is a IriStem, LiteralStem or LanguageStem with stem st and nodeIn(n, st).
        * vsv is a IriStemRange, LiteralStemRange or LanguageStemRange with stem st and exclusions excls and
          nodeIn(n, st) and there is no x in excls such that nodeIn(n, excl).
        * vsv is a Wildcard with exclusions excls and there is no x in excls such that nodeIn(n, excl).

    Note that ObjectLiteral is *not* typed in ShExJ.jsg, so we identify it by a lack of a 'type' variable

    .. note:: Mismatch with spec
        This won't work correctly if the stem value is passed in to nodeIn, as there will be no way to know whether
        we're matching an IRI or other type

    ... note:: Language issue
        The stem range spec shouldn't have the first element in the exclusions

    """
    vsv = map_object_literal(vsv)
    if isinstance_(vsv, ShExJ.objectValue):
        return objectValueMatches(n, vsv)

    if isinstance(vsv, ShExJ.Language):
        if vsv.languageTag is not None and isinstance(n, Literal) and n.language is not None:
            return n.language == vsv.languageTag
        else:
            return False

    if isinstance(vsv, ShExJ.IriStem):
        return nodeInIriStem(cntxt, n, vsv.stem)

    if isinstance(vsv, ShExJ.IriStemRange):
        exclusions = vsv.exclusions if vsv.exclusions is not None else []
        return nodeInIriStem(cntxt, n, vsv.stem) and not any(
            (uriref_matches_iriref(n, excl) if isinstance(excl, ShExJ.IRIREF) else
             uriref_startswith_iriref(n, excl.stem)) for excl in exclusions)

    if isinstance(vsv, ShExJ.LiteralStem):
        return nodeInLiteralStem(cntxt, n, vsv.stem)

    if isinstance(vsv, ShExJ.LiteralStemRange):
        exclusions = vsv.exclusions if vsv.exclusions is not None else []
        return nodeInLiteralStem(cntxt, n, vsv.stem) and not any(str(n) == excl for excl in exclusions)

    if isinstance(vsv, ShExJ.LanguageStem):
        return nodeInLanguageStem(cntxt, n, vsv.stem)

    if isinstance(vsv, ShExJ.LanguageStemRange):
        exclusions = vsv.exclusions if vsv.exclusions is not None else []
        return nodeInLanguageStem(cntxt, n, vsv.stem) and not any(str(n) == str(excl) for excl in exclusions)

    return False


def nodeInIriStem(_: Context, n: Node, s: ShExJ.IriStem) -> bool:
    """
       **nodeIn**: asserts that an RDF node n is equal to an RDF term s or is in a set defined by a
       :py:class:`ShExJ.IriStem`, :py:class:`LiteralStem` or :py:class:`LanguageStem`.

       The expression `nodeInIriStem(n, s)` is satisfied iff:
        #) `s` is a :py:class:`ShExJ.WildCard` or
        #) `n` is an :py:class:`rdflib.URIRef` and fn:starts-with(`n`, `s`)
    """
    return isinstance(s, ShExJ.Wildcard) or \
        (isinstance(n, URIRef) and uriref_startswith_iriref(n, str(s)))


def nodeInLiteralStem(_: Context, n: Node, s: ShExJ.LiteralStem) -> bool:
    """ http://shex.io/shex-semantics/#values

        **nodeIn**: asserts that an RDF node n is equal to an RDF term s or is in a set defined by a
        :py:class:`ShExJ.IriStem`, :py:class:`LiteralStem` or :py:class:`LanguageStem`.

        The expression `nodeInLiteralStem(n, s)` is satisfied iff:
         #) `s` is a :py:class:`ShExJ.WildCard` or
         #) `n` is an :py:class:`rdflib.Literal` and fn:starts-with(`n`, `s`)
     """
    return isinstance(s, ShExJ.Wildcard) or \
        (isinstance(n, Literal) and str(n.value).startswith(str(s)))


def nodeInLanguageStem(_: Context, n: Node, s: ShExJ.LanguageStem) -> bool:
    """ http://shex.io/shex-semantics/#values

        **nodeIn**: asserts that an RDF node n is equal to an RDF term s or is in a set defined by a
        :py:class:`ShExJ.IriStem`, :py:class:`LiteralStem` or :py:class:`LanguageStem`.

        The expression `nodeInLanguageStem(n, s)` is satisfied iff:
         #) `s` is a :py:class:`ShExJ.WildCard` or
         #) `n` is a language-tagged string and fn:starts-with(`n.language`, `s`)
    """
    return isinstance(s, ShExJ.Wildcard) or \
        (isinstance(n, Literal) and n.language is not None and str(n.language).startswith(str(s)))


def nodeInBnodeStem(_cntxt: Context, _n: Node, _s: str | ShExJ.Wildcard) -> bool:
    """ http://shex.io/shex-semantics/#values

        **nodeIn**: asserts that an RDF node n is equal to an RDF term s or is in a set defined by a
        :py:class:`ShExJ.IriStem`, :py:class:`LiteralStem` or :py:class:`LanguageStem`.

        The expression `nodeInBnodeStem(n, s)` is satisfied iff:
         #) `s` is a :py:class:`ShExJ.WildCard` or
         #) `n` is a language-tagged string and fn:starts-with(`n.language`, `s`)

    """
    # TODO: resolve issue #79 to figure out how to do this
    return False
