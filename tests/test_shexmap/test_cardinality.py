"""Cardinality above one: nothing caps how many values bind or materialize; regrouping,
transposition and reads of inherited bindings come out as the input's structure says; a
body that reads from unrelated lists is refused."""
import pytest
from rdflib import Graph, Literal, URIRef

from pyshex.shexmap import Bindings, MaterializationError, ThreadedMaterializer, bind, materialize

PREFIXES = """PREFIX : <http://a.example/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
V = "http://v.example/"
X = URIRef("http://a.example/x")
OUT = URIRef("http://a.example/out")


def turtle(text: str) -> Graph:
    return Graph().parse(data="PREFIX : <http://a.example/>\n" + text, format="turtle")


def frames(n: int, *variables: str) -> Bindings:
    """n frames, each binding every variable named to a value that says which frame."""
    return Bindings([{V + v: Literal(f"{v}{i}") for v in variables} for i in range(n)])


def objects(triples, local: str) -> list[str]:
    return sorted(str(o) for _, p, o in triples if str(p) == "http://a.example/" + local)


# -- binding: a repeated constraint or group takes every triple it matches -----------------

@pytest.mark.parametrize("n", [51, 60, 200])
def test_a_starred_constraint_binds_every_value(n):
    data = turtle(":x :tag " + ", ".join(f'"t{i}"' for i in range(n)) + " .")
    bound = bind(data, PREFIXES + "start = @:S\n:S { :tag . * %Map:{ v:t %} }", X)
    assert len(bound.frames()) == n
    assert bound.alternatives == 1


def test_a_plus_constraint_with_a_shape_binds_every_value():
    n = 70
    data = turtle(":x :item " + ", ".join(f'[ :a "a{i}" ; :b "b{i}" ]' for i in range(n)) + " .")
    bound = bind(data, PREFIXES + "start = @:S\n:S { :item { :a . %Map:{ v:a %} ; :b . %Map:{ v:b %} }+ }", X)
    got = bound.frames()
    assert len(got) == n
    assert all(str(f[V + "a"])[1:] == str(f[V + "b"])[1:] for f in got)     # each item stays one frame


def test_a_bounded_max_is_still_honoured():
    data = turtle(":x :tag " + ", ".join(f'"t{i}"' for i in range(3)) + " .")
    with pytest.raises(Exception):
        bind(data, PREFIXES + "start = @:S\n:S { :tag . {1,2} %Map:{ v:t %} }", X)


# -- materializing: the search reaches the materialization that uses every binding ----------

STAR = PREFIXES + "start = @:T\n:T { :label . * %Map:{ v:t %} }"


@pytest.mark.parametrize("n", [20, 50, 60])
def test_a_starred_constraint_emits_every_binding(n):
    m = ThreadedMaterializer(STAR)
    triples = m.materialize(frames(n, "t"), OUT)
    assert len(triples) == n
    assert m.chosen.consumed == n
    assert not m.last_report["exploration_truncated"]


def test_unread_bindings_beside_the_read_ones_change_nothing():
    # every item also binds v:u, which the output never reads: the frame model used to
    # accept once per repetition count here and truncate at max_accepts
    n = 60
    m = ThreadedMaterializer(STAR)
    triples = m.materialize(frames(n, "t", "u"), OUT)
    assert len(triples) == n
    assert m.chosen.consumed == n
    assert m.chosen is m.accepts[0]
    assert m.last_report["alternatives"] == 1


def test_a_starred_subshape_emits_every_frame():
    n = 60
    m = ThreadedMaterializer(PREFIXES + "start = @:T\n:T { :item @<I>* }\n<I> { :val . %Map:{ v:t %} }")
    triples = m.materialize(frames(n, "t"), OUT)
    assert len(objects(triples, "item")) == n
    assert len(objects(triples, "val")) == n


def test_max_repeat_caps_a_repetition_when_asked():
    m = ThreadedMaterializer(STAR, max_repeat=5)
    assert len(m.materialize(frames(10, "t"), OUT)) == 5


def test_a_perfect_accept_ends_the_search_at_once():
    m = ThreadedMaterializer(STAR)
    m.materialize(frames(30, "t"), OUT)
    assert m.last_report["alternatives"] == 1             # the greedy thread went straight to it


def test_end_to_end_with_many_values():
    n = 120
    data = turtle(":x :tag " + ", ".join(f'"t{i}"' for i in range(n)) + " .")
    bound = bind(data, PREFIXES + "start = @:S\n:S { :tag . * %Map:{ v:t %} }", X)
    out = materialize(STAR, bound, OUT)
    assert len(out) == n


# -- the structure of the input decides the structure of the output ------------------------

NESTED = PREFIXES + "start = @:P\n:P { :report { :no . %Map:{ v:no %} ; :result { :sys . %Map:{ v:sys %} }* }* }"
REPORTS = ':p :report [ :no "one" ; :result [ :sys 100 ], [ :sys 101 ] ], [ :no "two" ; :result [ :sys 110 ], [ :sys 111 ] ] .'


def test_a_nested_schema_maps_to_itself():
    bound = bind(turtle(REPORTS), NESTED, URIRef("http://a.example/p"))
    out = materialize(NESTED, bound, OUT)
    reports = list(out.objects(OUT, URIRef("http://a.example/report")))
    assert len(reports) == 2
    assert sorted(len(list(out.objects(r, URIRef("http://a.example/result")))) for r in reports) == [2, 2]


def test_sibling_lists_can_be_transposed():
    m = ThreadedMaterializer(PREFIXES + "start = @:T\n:T { :allB . * %Map:{ v:b %} ; :allA . * %Map:{ v:a %} }")
    triples = m.materialize(frames(2, "a", "b"), OUT)
    assert objects(triples, "allB") == ["b0", "b1"]
    assert objects(triples, "allA") == ["a0", "a1"]


def test_a_bound_value_must_satisfy_the_output_value_expression():
    m = ThreadedMaterializer(PREFIXES + "start = @:T\n:T { :n xsd:integer %Map:{ v:t %} }")
    with pytest.raises(MaterializationError):
        m.materialize(Bindings({V + "t": Literal("not a number")}), OUT)


# -- inherited bindings and unrelated lists (structural plan §1.2, §3.3) -------------------
# a parent's binding is read, never used up: it can be read at the parent and in every
# item, and twice in one item

PATIENT = Bindings([{V + "name": Literal("Sue")},
                    [{V + "sys": Literal("110"), V + "dia": Literal("70")},
                     {V + "sys": Literal("111"), V + "dia": Literal("71")}]])
A_EX = "http://a.example/"


def readings(graph_or_triples) -> list[tuple[str, str]]:
    """(sys, dia) per :bp node, in sys order."""
    triples = list(graph_or_triples)
    bps = {o for _, p, o in triples if str(p) == A_EX + "bp"}
    value = lambda s, local: next(str(o) for s2, p, o in triples if s2 == s and str(p) == A_EX + local)
    return sorted((value(b, "sys"), value(b, "dia")) for b in bps)


def test_a_parent_binding_read_once_per_item():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :bp { :sys . %Map:{ v:sys %} ; :who . %Map:{ v:name %} ; :dia . %Map:{ v:dia %} }* }")
    assert readings(m.materialize(PATIENT, OUT)) == [("110", "70"), ("111", "71")]


def test_a_parent_binding_read_at_the_parent_and_in_each_item():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :who . %Map:{ v:name %} ; "
                             ":bp { :sys . %Map:{ v:sys %} ; :who . %Map:{ v:name %} ; :dia . %Map:{ v:dia %} }* }")
    triples = m.materialize(PATIENT, OUT)
    assert readings(triples) == [("110", "70"), ("111", "71")]
    assert objects(triples, "who") == ["Sue", "Sue", "Sue"]


def test_a_parent_binding_read_twice_in_an_item():
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :bp { :sys . %Map:{ v:sys %} ; "
                             ":who . %Map:{ v:name %} ; :who2 . %Map:{ v:name %} ; :dia . %Map:{ v:dia %} }* }")
    assert readings(m.materialize(PATIENT, OUT)) == [("110", "70"), ("111", "71")]


def test_variables_from_unrelated_lists_are_refused():
    two_lists = Bindings([{}, [{V + "a": Literal("a1")}, {V + "a": Literal("a2")}],
                          [{V + "b": Literal("b1")}, {V + "b": Literal("b2")}]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :pair { :x . %Map:{ v:a %} ; :y . %Map:{ v:b %} }* }")
    with pytest.raises(MaterializationError, match="unrelated lists"):
        m.materialize(two_lists, OUT)


def test_a_deeper_variable_read_without_a_repetition_fails():
    # "which one?" is not guessed: the read fails, as an unbound variable does
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :first . %Map:{ v:sys %} }")
    with pytest.raises(MaterializationError, match="sys"):
        m.materialize(PATIENT, OUT)


def test_a_repetition_over_a_deeper_list_flattens():
    reports = Bindings([{}, [[{V + "no": Literal("one")}, [{V + "sys": Literal("100")}, {V + "sys": Literal("101")}]],
                             [{V + "no": Literal("two")}, [{V + "sys": Literal("110")}]]]])
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :all . * %Map:{ v:sys %} }")
    assert objects(m.materialize(reports, OUT), "all") == ["100", "101", "110"]
    # and a group per reading takes its label from the report above it
    m = ThreadedMaterializer(PREFIXES + "start = @:Out\n:Out { :g { :label . %Map:{ v:no %} ; :reading . %Map:{ v:sys %} }* }")
    triples = m.materialize(reports, OUT)
    labels = {str(o) for _, p, o in triples if str(p) == A_EX + "label"}
    assert len(objects(triples, "g")) == 3 and labels == {"one", "two"}

