from ShExJSG import ShExJ
from ShExJSG.ShExJ import IRIREF
from rdflib import Graph, URIRef

from pyshex.shape_expressions_language.p5_2_validation_definition import isValid
from pyshex.shape_expressions_language.p5_context import Context
from pyshex.shapemap_structure_and_language.p3_shapemap_structure import FixedShapeMap, ShapeAssociation, START, \
    START_TYPE
from pyshex.utils.schema_loader import SchemaLoader


def evaluate(g: Graph,
             schema: str | ShExJ.Schema,
             focus: str | URIRef | IRIREF | None,
             start: str | URIRef | IRIREF | START | START_TYPE | None = None,
             debug_trace: bool = False) -> tuple[bool, str | None]:
    """ Evaluate focus node `focus` in graph `g` against shape `shape` in ShEx schema `schema`

    :param g: Graph containing RDF
    :param schema: ShEx Schema -- if str, it will be parsed
    :param focus: focus node in g. If not specified, all URI subjects in G will be evaluated.
    :param start: Starting shape.  If omitted, the Schema start shape is used
    :param debug_trace: Turn on debug tracing
    :return: None if success or failure reason if failure
    """
    if isinstance(schema, str):
        schema = SchemaLoader().loads(schema)
    if schema is None:
        return False, "Error parsing schema"
    if not isinstance(focus, URIRef):
        focus = URIRef(str(focus))
    if start is None:
        start = str(schema.start) if schema.start else None
    if start is None:
        return False, "No starting shape"
    if not isinstance(start, IRIREF) and start is not START and start is not START_TYPE:
        start = IRIREF(str(start))
    cntxt = Context(g, schema)
    cntxt.debug_context.debug = debug_trace
    map_ = FixedShapeMap()
    map_.add(ShapeAssociation(focus, start))
    test_result, reasons = isValid(cntxt, map_)
    return test_result, '\n'.join(reasons)
