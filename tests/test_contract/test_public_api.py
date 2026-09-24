"""Freeze the public API of PyShEx so that PyPI releases stay backward compatible.

Compatible evolution passes: appending parameters that have defaults, adding new
keyword-only parameters, adding new exports, or adding new CLI options.
Everything else fails: removing or renaming a name, reordering parameters, making
an optional parameter required, changing a default, or dropping a CLI option.
See README.md in this directory for what to do when a test here fails.
"""
import importlib
import inspect
from importlib import metadata

import pytest

REQUIRED = inspect.Parameter.empty
ANY_DEFAULT = object()  # parameter must stay optional, but its default value may change
VAR_POS = "*"
VAR_KW = "**"

# name -> expected leading parameters, as (name, default) pairs, or VAR_POS/VAR_KW markers.
SIGNATURES = {
    "pyshex.shex_evaluator:ShExEvaluator.__init__": [
        ("self", REQUIRED), ("rdf", None), ("schema", None), ("focus", None), ("start", None),
        ("rdf_format", "turtle"), ("debug", False), ("debug_slurps", False), ("over_slurp", None),
        ("output_sink", None),
    ],
    "pyshex.shex_evaluator:ShExEvaluator.evaluate": [
        ("self", REQUIRED), ("rdf", None), ("shex", None), ("focus", None), ("start", None),
        ("rdf_format", None), ("debug", None), ("debug_slurps", None), ("over_slurp", None),
        ("output_sink", None),
    ],
    "pyshex.shex_evaluator:evaluate_cli": [("argv", None), ("prog", None)],
    "pyshex.shex_evaluator:genargs": [("prog", None)],
    "pyshex.evaluate:evaluate": [
        ("g", REQUIRED), ("schema", REQUIRED), ("focus", REQUIRED), ("start", None), ("debug_trace", False),
    ],
    "pyshex.utils.schema_loader:SchemaLoader.__init__": [
        ("self", REQUIRED), ("base_location", None), ("redirect_location", None), ("schema_type_suffix", None),
    ],
    "pyshex.utils.schema_loader:SchemaLoader.load": [
        ("self", REQUIRED), ("schema_file", REQUIRED), ("schema_location", None),
    ],
    "pyshex.utils.schema_loader:SchemaLoader.loads": [("self", REQUIRED), ("schema_txt", REQUIRED)],
    "pyshex.utils.schema_loader:SchemaLoader.location_rewrite": [("self", REQUIRED), ("schema_location", REQUIRED)],
    "pyshex.prefixlib:PrefixLibrary.__init__": [("self", REQUIRED), ("schema", None), VAR_KW],
    "pyshex.prefixlib:PrefixLibrary.add_shex": [("self", REQUIRED), ("schema", REQUIRED)],
    "pyshex.prefixlib:PrefixLibrary.add_rdf": [("self", REQUIRED), ("rdf", REQUIRED), ("format", "turtle")],
    "pyshex.prefixlib:PrefixLibrary.add_bindings_to": [("self", REQUIRED), ("g", REQUIRED)],
    "pyshex.prefixlib:PrefixLibrary.add_to_object": [("self", REQUIRED), ("target", REQUIRED), ("override", False)],
    "pyshex.prefixlib:PrefixLibrary.nsname": [("self", REQUIRED), ("uri", REQUIRED)],
    "pyshex.user_agent:SlurpyGraphWithAgent": [("endpoint", REQUIRED), VAR_POS],
    "pyshex.user_agent:SPARQLWrapperWithAgent.__init__": [
        ("self", REQUIRED), ("endpoint", REQUIRED), ("updateEndpoint", None), ("returnFormat", None),
        ("defaultGraph", None), ("agent", ANY_DEFAULT),
    ],
}

# Keyword-only parameters that callers may pass by name: name -> {param: default}
KEYWORD_ONLY = {
    "pyshex.user_agent:SlurpyGraphWithAgent": {"persistent_bnodes": False, "agent": None, "gdb_slurper": False},
}

EXPORTS = {
    "pyshex": ["ShExEvaluator", "PrefixLibrary", "standard_prefixes", "known_prefixes"],
    "pyshex.shex_evaluator": ["ShExEvaluator", "EvaluationResult", "evaluate_cli", "genargs"],
    "pyshex.evaluate": ["evaluate"],
    "pyshex.utils.schema_loader": ["SchemaLoader"],
    "pyshex.prefixlib": ["PrefixLibrary", "standard_prefixes", "known_prefixes"],
    "pyshex.user_agent": ["UserAgent", "SlurpyGraphWithAgent", "SPARQLWrapperWithAgent"],
    "pyshex.shapemap_structure_and_language.p3_shapemap_structure": [
        "START", "START_TYPE", "FixedShapeMap", "ShapeAssociation",
    ],
}

CLI_OPTIONS = [
    "--format", "--start", "--usetype", "--startpredicate", "--focus", "--allsubjects", "--debug", "--slurper",
    "--gdbslurper", "--flattener", "--sparql", "--stoponerror", "--stopafter", "--printsparql",
    "--printsparqlresults", "--graphname", "--persistbnodes", "--useragent",
    "-f", "-s", "-ut", "-sp", "-fn", "-A", "-d", "-ss", "-ssg", "-cf", "-sq", "-se", "-ps", "-pr", "-gn", "-pb",
]


def resolve(target: str):
    module_name, _, attr_path = target.partition(":")
    obj = importlib.import_module(module_name)
    for part in attr_path.split(".") if attr_path else []:
        obj = getattr(obj, part)
    return obj


def signature_problems(func, expected) -> list[str]:
    actual = list(inspect.signature(func).parameters.values())
    problems = []
    for i, exp in enumerate(expected):
        if i >= len(actual):
            problems.append(f"parameter #{i} {exp!r} was removed")
            continue
        act = actual[i]
        if exp in (VAR_POS, VAR_KW):
            kind = inspect.Parameter.VAR_POSITIONAL if exp == VAR_POS else inspect.Parameter.VAR_KEYWORD
            if act.kind != kind:
                problems.append(f"parameter #{i} should be {exp}, found {act}")
            continue
        name, default = exp
        if act.name != name:
            problems.append(f"parameter #{i} was renamed or moved: expected {name!r}, found {act.name!r}")
        elif act.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD,):
            problems.append(f"parameter {name!r} is no longer positional-or-keyword ({act.kind.description})")
        elif default is REQUIRED:
            pass  # a required parameter may become optional
        elif act.default is REQUIRED:
            problems.append(f"parameter {name!r} became required")
        elif default is not ANY_DEFAULT and act.default != default:
            problems.append(f"default of {name!r} changed from {default!r} to {act.default!r}")
    for act in actual[len(expected):]:
        if act.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if act.default is REQUIRED:
            problems.append(f"new parameter {act.name!r} must have a default")
    return problems


@pytest.mark.parametrize("target", sorted(SIGNATURES))
def test_signature_is_backward_compatible(target):
    problems = signature_problems(resolve(target), SIGNATURES[target])
    assert not problems, f"{target}: " + "; ".join(problems)


@pytest.mark.parametrize("target", sorted(KEYWORD_ONLY))
def test_keyword_parameters_still_accepted(target):
    params = inspect.signature(resolve(target)).parameters
    for name, default in KEYWORD_ONLY[target].items():
        assert name in params, f"{target}: keyword parameter {name!r} was removed"
        assert params[name].default == default, f"{target}: default of {name!r} changed"


@pytest.mark.parametrize("module_name", sorted(EXPORTS))
def test_exports_still_present(module_name):
    module = importlib.import_module(module_name)
    missing = [name for name in EXPORTS[module_name] if not hasattr(module, name)]
    assert not missing, f"{module_name} no longer exports {missing}"


def test_top_level_evaluator_is_the_real_class():
    import pyshex
    from pyshex.shex_evaluator import ShExEvaluator

    assert pyshex.ShExEvaluator is ShExEvaluator


@pytest.mark.parametrize("prop", ["rdf", "schema", "focus", "foci", "start"])
def test_evaluator_properties(prop):
    from pyshex.shex_evaluator import ShExEvaluator

    assert isinstance(inspect.getattr_static(ShExEvaluator, prop), property)


def test_evaluation_result_fields():
    from pyshex.shex_evaluator import EvaluationResult

    assert issubclass(EvaluationResult, tuple)
    assert EvaluationResult._fields[:4] == ("result", "focus", "start", "reason")


def test_prefix_library_deprecated_alias_kept():
    from pyshex.prefixlib import PrefixLibrary

    assert callable(PrefixLibrary.add_bindings)


def test_cli_options_still_accepted():
    from pyshex.shex_evaluator import genargs

    parser = genargs()
    known = {opt for action in parser._actions for opt in action.option_strings}
    missing = sorted(set(CLI_OPTIONS) - known)
    assert not missing, f"shexeval no longer accepts {missing}"
    positionals = [a.dest for a in parser._actions if not a.option_strings]
    assert positionals == ["rdf", "shex"]


def test_console_script_entry_point():
    try:
        dist = metadata.distribution("PyShEx")
    except metadata.PackageNotFoundError:  # running from a source tree that was never installed
        pytest.skip("PyShEx distribution metadata not installed")
    scripts = {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}
    assert scripts.get("shexeval") == "pyshex.shex_evaluator:evaluate_cli"


SHEX = """PREFIX ex: <http://example.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
start = @ex:Person
ex:Person { ex:name xsd:string }
"""
TTL = """@prefix ex: <http://example.org/> .
ex:alice ex:name "Alice" .
ex:bob ex:name 17 .
"""


@pytest.mark.parametrize("focus, expected_rc", [("http://example.org/alice", 0), ("http://example.org/bob", 1)])
def test_cli_exit_codes(tmp_path, capsys, focus, expected_rc):
    from pyshex.shex_evaluator import evaluate_cli

    (tmp_path / "s.shex").write_text(SHEX)
    (tmp_path / "d.ttl").write_text(TTL)
    rc = evaluate_cli([str(tmp_path / "d.ttl"), str(tmp_path / "s.shex"), "-fn", focus])
    assert rc == expected_rc


def test_cli_requires_a_focus(tmp_path, capsys):
    from pyshex.shex_evaluator import evaluate_cli

    (tmp_path / "s.shex").write_text(SHEX)
    (tmp_path / "d.ttl").write_text(TTL)
    assert evaluate_cli([str(tmp_path / "d.ttl"), str(tmp_path / "s.shex")]) == 4
    assert evaluate_cli([str(tmp_path / "d.ttl"), str(tmp_path / "s.shex"), "-A"]) == 1
