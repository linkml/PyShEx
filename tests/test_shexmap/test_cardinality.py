"""Cardinality above one: nothing caps how many values bind or materialize, and the frame
model's known limits are pinned down as strict xfails, so they flip when a redesign lands."""
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


def test_advances_that_forfeit_bindings_still_reach_the_full_materialization():
    # each advance abandons an unused v:u, so every repetition count accepts before the
    # next one is tried; the full materialization is found last and must still win
    n = 60
    m = ThreadedMaterializer(STAR)
    triples = m.materialize(frames(n, "t", "u"), OUT)
    assert len(triples) == n
    assert m.chosen.consumed == n
    assert m.chosen in m.accepts
    assert len(m.accepts) == 20                           # the best max_accepts are kept ...
    assert sorted(a.consumed for a in m.accepts) == list(range(41, 61))
    assert m.last_report["alternatives"] == n + 1         # ... out of every distinct accept


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


# -- limits of the frame model, as documented ----------------------------------------------

NESTED = PREFIXES + "start = @:P\n:P { :report { :no . %Map:{ v:no %} ; :result { :sys . %Map:{ v:sys %} }* }* }"
REPORTS = ':p :report [ :no "one" ; :result [ :sys 100 ], [ :sys 101 ] ], [ :no "two" ; :result [ :sys 110 ], [ :sys 111 ] ] .'


@pytest.mark.xfail(strict=True, reason="frame model: a report's :no is copied into each reading's frame, "
                                       "so one group per reading uses 'more' bindings")
def test_a_nested_schema_maps_to_itself():
    bound = bind(turtle(REPORTS), NESTED, URIRef("http://a.example/p"))
    out = materialize(NESTED, bound, OUT)
    reports = list(out.objects(OUT, URIRef("http://a.example/report")))
    assert len(reports) == 2
    assert sorted(len(list(out.objects(r, URIRef("http://a.example/result")))) for r in reports) == [2, 2]


@pytest.mark.xfail(strict=True, reason="frame model: the cursor never moves back, so a second repetition "
                                       "cannot revisit the frames the first one passed")
def test_sibling_lists_can_be_transposed():
    m = ThreadedMaterializer(PREFIXES + "start = @:T\n:T { :allB . * %Map:{ v:b %} ; :allA . * %Map:{ v:a %} }")
    triples = m.materialize(frames(2, "a", "b"), OUT)
    assert objects(triples, "allB") == ["b0", "b1"]
    assert objects(triples, "allA") == ["a0", "a1"]


@pytest.mark.xfail(strict=True, reason="bound values are not checked against the output constraint's "
                                       "value expression")
def test_a_bound_value_must_satisfy_the_output_value_expression():
    m = ThreadedMaterializer(PREFIXES + "start = @:T\n:T { :n xsd:integer %Map:{ v:t %} }")
    with pytest.raises(MaterializationError):
        m.materialize(Bindings({V + "t": Literal("not a number")}), OUT)
