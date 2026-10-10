"""Static checks of a schema pair (pyshex.shexmap.analyse): which pairs map coherently, and
why not, before any data."""
import json
from pathlib import Path

import pytest

from pyshex.shexmap import analyse
from pyshex.shexmap.cli import main
from tests.test_shexmap.test_examples import MANIFEST, label, node_and_shape, text

PREFIXES = """PREFIX : <http://a.example/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX v: <http://v.example/>
PREFIX Map: <http://shex.io/extensions/Map/#>
"""
NESTED_IN = PREFIXES + "start = @:P\n:P { :name . %Map:{ v:name %} ; :report { :no . %Map:{ v:no %} ; :result { :sys . %Map:{ v:sys %} }* }* }"


def out(schema: str) -> str:
    return PREFIXES + "start = @:Out\n" + schema


@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_every_example_pair_is_coherent(entry):
    _, start = node_and_shape(entry["queryMap"])
    _, out_shape = node_and_shape(entry["outputShapeMap"])
    report = analyse(text(entry, "schema"), text(entry, "outputSchema"), input_start=start, output_start=out_shape,
                     static_vars=list(entry.get("staticVars", {})))
    assert report.errors == [], str(report)


@pytest.mark.parametrize("entry", MANIFEST, ids=label)
def test_every_schema_maps_to_itself(entry):
    _, start = node_and_shape(entry["queryMap"])
    report = analyse(text(entry, "schema"), text(entry, "schema"), input_start=start, output_start=start)
    assert report.errors == [], str(report)
    assert report.warnings == []                                   # every binding is read back


def test_regrouping_and_flattening_are_coherent():
    for schema in [":Out { :group @<G>* }\n<G> { :label . %Map:{ v:no %} ; :reading . + %Map:{ v:sys %} }",
                   ":Out { :who . %Map:{ v:name %} ; :all . * %Map:{ v:sys %} }",
                   ":Out { :g { :label . %Map:{ v:no %} ; :reading . %Map:{ v:sys %} }* }",
                   ":Out { :bp { :sys . %Map:{ v:sys %} ; :who . %Map:{ v:name %} }* }"]:
        report = analyse(NESTED_IN, out(schema))
        assert report.errors == [], str(report)


def test_a_deeper_variable_read_without_a_repetition_is_which_one():
    report = analyse(NESTED_IN, out(":Out { :first . %Map:{ v:sys %} }"))
    assert len(report.errors) == 1 and "which one" in report.errors[0]
    assert "each :report / :result" in report.errors[0]


def test_an_optional_over_a_deeper_variable_takes_the_first():
    # `?` is a repetition of at most one: it iterates the list and stops
    report = analyse(NESTED_IN, out(":Out { :first . ? %Map:{ v:sys %} }"))
    assert report.errors == []


def test_unrelated_lists_are_named():
    two_lists = PREFIXES + "start = @:S\n:S { :a . * %Map:{ v:a %} ; :b { :v . %Map:{ v:b %} }* }"
    report = analyse(two_lists, out(":Out { :pair { :x . %Map:{ v:a %} ; :y . %Map:{ v:b %} }* }"))
    assert len(report.errors) == 1
    assert "unrelated lists" in report.errors[0] and "v:a" in report.errors[0] and "v:b" in report.errors[0]
    assert "each :a" in report.errors[0] and "each :b" in report.errors[0]


def test_a_variable_from_a_sibling_list_is_not_in_scope():
    two_lists = PREFIXES + "start = @:S\n:S { :a . * %Map:{ v:a %} ; :b { :v . %Map:{ v:b %} }* }"
    report = analyse(two_lists, out(":Out { :x { :va . %Map:{ v:a %} ; :vb . %Map:{ v:b %} }* }"))
    assert any("unrelated lists" in e for e in report.errors)


def test_unbound_and_unused_variables():
    report = analyse(NESTED_IN, out(":Out { :who . %Map:{ v:name %} ; :oops . %Map:{ v:typo %} }"))
    assert [e for e in report.errors if "never binds" in e and "typo" in e]
    assert [w for w in report.warnings if "v:sys" in w and "never reads" in w]
    report = analyse(NESTED_IN, out(":Out { :who . %Map:{ v:name %} ; :konst . %Map:{ v:stat %} }"),
                     static_vars=["http://v.example/stat", "http://v.example/unused"])
    assert not [e for e in report.errors if "stat" in e]
    assert [w for w in report.warnings if "unused" in w and "static" in w]


def test_a_variable_bound_at_two_sites_is_an_error():
    twice = PREFIXES + "start = @:S\n:S { :n . %Map:{ v:x %} ; :item { :n . %Map:{ v:x %} }* }"
    report = analyse(twice, out(":Out { :y . %Map:{ v:x %} }"))
    assert [e for e in report.errors if "two places" in e]


def test_id_checks():
    assert [e for e in analyse(NESTED_IN, out(":Out { :n . %Map:{ id(v:no) %} }")).errors if "shape-valued" in e]
    assert [e for e in analyse(NESTED_IN, out(":Out { :g @<G> %Map:{ id(v:name) %} %Map:{ v:name %} }\n<G> { :k [:c] }")).errors
            if "only Map code" in e]
    assert [e for e in analyse(NESTED_IN, out(":Out { :g @<G> %Map:{ id(@node) %} }\n<G> { :k [:c] }")).errors
            if "@node" in e]
    report = analyse(NESTED_IN, out(":Out { :g @<G>* %Map:{ id(@node) %} }\n<G> { :label . %Map:{ v:no %} ; :r . * %Map:{ v:sys %} }"))
    assert report.errors == [], str(report)


def test_undefined_and_abstract_output_shapes():
    assert [e for e in analyse(NESTED_IN, out(":Out { :g @<Nowhere> }")).errors if "does not define" in e]
    assert [e for e in analyse(NESTED_IN, out(":Out { :g @<A> }\nABSTRACT <A> { :k [:c] }")).errors if "abstract" in e]


def test_cli_check(tmp_path, capsys):
    (tmp_path / "in.shex").write_text(NESTED_IN, encoding="utf-8")
    (tmp_path / "good.shex").write_text(out(":Out { :group @<G>* }\n<G> { :label . %Map:{ v:no %} ; :reading . + %Map:{ v:sys %} }"),
                                        encoding="utf-8")
    (tmp_path / "bad.shex").write_text(out(":Out { :first . %Map:{ v:sys %} }"), encoding="utf-8")
    assert main(["--check", "-s", str(tmp_path / "in.shex"), "-t", str(tmp_path / "good.shex")]) == 0
    assert "warning" in capsys.readouterr().out                   # v:name is never read
    assert main(["--check", "-s", str(tmp_path / "in.shex"), "-t", str(tmp_path / "bad.shex")]) == 1
    assert "which one" in capsys.readouterr().out


def test_template_variables_are_checked_like_the_others():
    report = analyse(NESTED_IN, out(":Out { :r @<R>* %Map:{ id(<http://a.example/report/{v:no}>) %} }\n<R> { :k [:c] }"))
    assert report.errors == [], str(report)
    report = analyse(NESTED_IN, out(":Out { :r @<R>* %Map:{ id(<http://a.example/report/{v:nope}>) %} }\n<R> { :k [:c] }"))
    assert [e for e in report.errors if "never binds" in e and "nope" in e]
