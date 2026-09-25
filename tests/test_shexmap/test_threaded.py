"""The threaded materializer, ported from shex.js's ThreadedMaterializer-test.js."""
import json
from pathlib import Path

import pytest
from rdflib import Literal, URIRef

from pyshex.shexmap import MaterializationError, ThreadedMaterializer, normalize
from pyshex.shexmap.bindings import loads

EX = Path(__file__).parent / "examples"
A = "http://a.example/"
PREFIXES = "PREFIX : <http://a.example/>\nPREFIX Map: <http://shex.io/extensions/Map/#>\n"


def tree(obj):
    return loads(json.dumps(obj)).tree


def lit(v: str) -> dict:
    return {"value": v}


def preds(triples) -> list[str]:
    return sorted(str(p).replace(A, ":") for _, p, _ in triples)


def run(schema: str, bindings, root="_:root", **options):
    m = ThreadedMaterializer(PREFIXES + schema, **options)
    return m, m.materialize(tree(bindings), root)


# -- binding tree normalization ----------------------------------------------------------

def test_singletons_are_distributed_into_repeated_frames():
    frames = normalize(loads((EX / "BPPatient-multi-bindings-bindings.json").read_text()).tree)
    name = "http://shex.io/extensions/Map/#BPDAM-name"
    assert len(frames) == 2
    assert all(f[name] == Literal("Sue") for f in frames)
    assert [str(f["http://shex.io/extensions/Map/#BPDAM-sysVal"]) for f in frames] == ["110", "111"]


def test_nested_groups_flatten_keeping_group_bindings_with_their_frames():
    frames = normalize(loads((EX / "BPPatient-2-levels-bindings.json").read_text()).tree)
    assert len(frames) == 4
    assert [str(f["http://shex.io/extensions/Map/#BPDAM-reportNo"]) for f in frames] == ["one", "one", "two", "two"]
    assert all(str(f["http://shex.io/extensions/Map/#BPDAM-name"]) == "Sue" for f in frames)


# -- frame advances and acceptance --------------------------------------------------------

CARD = """start = @<Card>
<Card> { :fullName . %Map:{ :name %} ;
         ( :phone @<T> | :mbox @<E> )+ }
<T> { :use . %Map:{ :use %} ; :val . %Map:{ :tel %} }
<E> { :use . %Map:{ :use %} ; :val . %Map:{ :email %} }
"""
CONTACTS = [{A + "name": lit("Ann")},
            [{A + "use": lit("work"), A + "email": lit("w@x")},
             {A + "use": lit("home"), A + "email": lit("h@x")},
             {A + "use": lit("home"), A + "tel": lit("+1")}]]


def test_cross_frame_pairing_does_not_beat_in_frame_consumption():
    m, triples = run(CARD, CONTACTS, "tag:card")
    assert sorted(str(o) for _, p, o in triples if str(p) == A + "val") == ["+1", "h@x", "w@x"]
    assert m.chosen.consumed == 7
    mix = [a for a in m.accepts if a.skipped == 4]
    assert mix and mix[0].consumed == 3        # frame 0's :use with frame 2's :tel, demoted


def test_constant_only_variants_collapse_onto_one_accept():
    m, triples = run("start = @<S>\n<S> { :a [:c1]? ; :b [:c2]? ; :v . %Map:{ :v1 %} }", {A + "v1": lit("x")})
    assert len(m.accepts) == 1
    assert len(triples) == 3


def test_a_tie_is_exposed_and_the_greedy_winner_kept():
    m, triples = run("start = @<S>\n<S> { :p . %Map:{ :v1 %} | :q . %Map:{ :v2 %} }",
                     {A + "v1": lit("x"), A + "v2": lit("y")})
    assert len(m.accepts) == 2
    assert m.chosen is m.accepts[0]
    assert preds(triples) == [":p"]
    assert m.last_report["alternatives"] == 2


# -- backtracking ------------------------------------------------------------------------

def test_an_abandoned_optional_group_releases_its_bindings():
    _, triples = run("start = @<S>\n<S> { (:a . %Map:{ :v1 %}; :b . %Map:{ :v2 %})? ; :c . %Map:{ :v1 %} }",
                     {A + "v1": lit("x")})
    assert preds(triples) == [":c"]


def test_an_unbound_variable_falls_through_to_the_next_disjunct():
    _, triples = run("start = @<S>\n<S> { :a . %Map:{ :v2 %} | :b . %Map:{ :v1 %} }", {A + "v1": lit("x")})
    assert preds(triples) == [":b"]


def test_a_starred_subshape_stops_when_bindings_run_out():
    _, triples = run("start = @<S>\n<S> { :item @<I>* }\n<I> { :tag [:const]; :val . %Map:{ :v1 %} }",
                     [[{A + "v1": lit("x")}, {A + "v1": lit("y")}]])
    assert len(triples) == 6
    assert sorted(str(o) for _, p, o in triples if str(p) == A + "val") == ["x", "y"]


def test_no_materialization_reports_the_failure():
    with pytest.raises(MaterializationError, match="v2"):
        run("start = @<S>\n<S> { :a . %Map:{ :v2 %} }", {A + "v1": lit("x")})


def test_failure_records_reference_the_triple_constraint():
    with pytest.raises(MaterializationError) as e:
        run("start = @<S>\n<S> { :a . %Map:{ :v2 %} }", {A + "v1": lit("x")})
    failure = next(f for f in e.value.failures if f.get("tc") is not None)
    assert str(failure["tc"].predicate) == A + "a"


def test_never_bound_variables_are_reported_when_a_star_collapses():
    m, triples = run("start = @<S>\n<S> { :item @<I>* }\n<I> { :val . %Map:{ :v1 %}; :oops . %Map:{ :typo %} }",
                     [[{A + "v1": lit("a")}, {A + "v1": lit("b")}]],
                     static_vars={A + "unrelated": Literal("x")})
    assert triples == []
    assert [f["variable"] for f in m.last_report["unbound_variables"]] == [A + "typo"]
    assert str(m.last_report["unbound_variables"][0]["tc"].predicate) == A + "oops"
    assert m.last_report["unused_statics"] == [A + "unrelated"]


def test_the_report_is_quiet_on_healthy_runs():
    m, triples = run("start = @<S>\n<S> { :item @<I>* }\n<I> { :val . %Map:{ :v1 %}; :konst . %Map:{ :stat %} }",
                     [[{A + "v1": lit("a")}, {A + "v1": lit("b")}]], static_vars={A + "stat": Literal("s")})
    assert triples
    assert m.last_report["unbound_variables"] == []
    assert m.last_report["unused_statics"] == []


# -- shape expression composition ---------------------------------------------------------

def test_shape_and_conjuncts_share_the_subject():
    _, triples = run("start = @<S> AND { :t [:const] }\n<S> { :a . %Map:{ :v1 %} }", {A + "v1": lit("x")}, "tag:root")
    assert len(triples) == 2
    assert {s for s, _, _ in triples} == {URIRef("tag:root")}


def test_binding_free_subshapes_repeat_once():
    _, triples = run("start = @<S>\n<S> { :item @<I>* }\n<I> { :tag [:const] }", {})
    assert len(triples) == 2


def test_static_vars_are_never_used_up():
    _, triples = run("start = @<S>\n<S> { :a . %Map:{ :v9 %}; :b . %Map:{ :v9 %} }", {},
                     static_vars={A + "v9": Literal("s")})
    assert len(triples) == 2


def test_a_cycle_of_references_is_refused_by_name():
    m = ThreadedMaterializer(PREFIXES + "<A> @<B> OR { :p [1] }\n<B> @<A> OR { :q [2] }\n")
    with pytest.raises(MaterializationError, match="cycle in shape expressions: .*A -> .*B -> .*A"):
        m.materialize({}, "_:x", start="A")


def test_shape_not_is_refused():
    m = ThreadedMaterializer(PREFIXES + "<A> NOT { :p [1] }\n")
    with pytest.raises(MaterializationError, match="ShapeNot synthesis"):
        m.materialize({}, "_:x", start="A")


# -- static-only optional subshapes -------------------------------------------------------

ISLAND = "<S> { :name . %Map:{ :n %} ; :seen @<T> ? }\n<T> { :kind [:fixed] }"


def test_a_static_only_optional_subshape_is_emitted_by_default():
    m = ThreadedMaterializer(PREFIXES + ISLAND)
    assert preds(m.materialize(tree({A + "n": lit("Bob")}), "_:x", start="S")) == [":kind", ":name", ":seen"]


def test_it_is_left_out_where_islands_must_consume_bindings():
    m = ThreadedMaterializer(PREFIXES + ISLAND, require_bindings_in_subshapes=True)
    assert preds(m.materialize(tree({A + "n": lit("Bob")}), "_:x", start="S")) == [":name"]


# -- choosing among accepts ---------------------------------------------------------------

def _has(triples, local: str) -> bool:
    return any(str(p).endswith("#" + local) for _, p, _ in triples)


def test_the_first_disjunct_wins_by_default():
    m = ThreadedMaterializer((EX / "card-flat-schema.shex").read_text())
    triples = m.materialize(loads((EX / "ambiguous-bindings.json").read_text()), "_:c")
    assert len(m.accepts) == 2
    assert _has(triples, "phone")


def test_a_caller_comparator_decides():
    m = ThreadedMaterializer((EX / "card-flat-schema.shex").read_text(),
                             prefer=lambda a, b: _has(b.triples, "mbox") - _has(a.triples, "mbox"))
    triples = m.materialize(loads((EX / "ambiguous-bindings.json").read_text()), "_:c")
    assert _has(triples, "mbox")
    assert m.chosen.triples is triples
