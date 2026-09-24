"""Keep the runtime dependency footprint small and deliberate.

LinkML installs PyShEx for every user, so anything PyShEx pulls in lands in every
LinkML environment. These tests fail when the set of runtime packages changes, on any
platform or Python version the lockfile covers, until someone reviews and edits the
allowlist below.
"""
import ast
import re
from importlib import metadata

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tests.test_policy._repo import ROOT, lockfile, pyproject

# Every package that can be installed at runtime, with why it is acceptable.
# Changing this list is a reviewable decision: explain the new dependency in the PR.
ALLOWED_RUNTIME_PACKAGES = {
    # direct dependencies
    "cfgraph": "RDF collection flattening graph (pure Python, tiny)",
    "chardet": "declared direct dependency",
    "pyshexc": "ShExC parser",
    "rdflib-shim": "rdflib compatibility shim",
    "requests": "HTTP fetching of schemas and data",
    "shexjsg": "ShExJ object model",
    "sparqlslurper": "SPARQL-backed graph",
    "sparqlwrapper": "SPARQL endpoint client",
    "urllib3": "declared direct dependency",
    # transitive
    "antlr4-python3-runtime": "parser runtime for pyshexc and pyjsg",
    "certifi": "via requests",
    "charset-normalizer": "via requests",
    "idna": "via requests",
    "isodate": "via rdflib on Python < 3.11",
    "jsonasobj": "via pyshexc and pyjsg",
    "pyjsg": "via pyshexc and shexjsg",
    "pyparsing": "via rdflib",
    "rdflib": "via cfgraph, rdflib-shim, sparqlslurper",
    "rdflib-jsonld": "via rdflib-shim",
}

# Distributions that pyshex imports directly but only gets transitively.
# Each is a latent risk: if the intermediate package drops it, pyshex breaks.
# Prefer declaring them in pyproject.toml; do not add to this list.
IMPORTED_BUT_UNDECLARED = {"rdflib", "pyjsg", "jsonasobj"}

# Distributions declared in pyproject.toml that pyshex never imports.
DECLARED_BUT_NOT_IMPORTED = {"chardet", "urllib3"}

UPPER_BOUND_OPERATORS = {"<", "<=", "==", "===", "~="}


def direct_requirements() -> list[Requirement]:
    return [Requirement(r) for r in pyproject()["project"]["dependencies"]]


def locked_runtime_closure() -> set[str]:
    packages = {canonicalize_name(p["name"]): p for p in lockfile()["package"]}
    seen: set[str] = set()
    todo = [canonicalize_name(d["name"]) for d in packages["pyshex"].get("dependencies", [])]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo += [canonicalize_name(d["name"]) for d in packages[name].get("dependencies", [])]
    return seen


def test_runtime_closure_matches_allowlist():
    closure = locked_runtime_closure()
    allowed = {canonicalize_name(n) for n in ALLOWED_RUNTIME_PACKAGES}
    new = sorted(closure - allowed)
    gone = sorted(allowed - closure)
    assert not new, (
        f"New runtime dependencies {new} would be installed for every LinkML user. "
        "If they are intended and lightweight, add them to ALLOWED_RUNTIME_PACKAGES with a reason."
    )
    assert not gone, f"{gone} are no longer runtime dependencies; remove them from ALLOWED_RUNTIME_PACKAGES."


def test_no_extras_pull_in_hidden_dependencies():
    assert not pyproject()["project"].get("optional-dependencies"), (
        "Extras are fine, but add their packages to the allowlist review first."
    )


def test_direct_dependencies_have_no_upper_bounds():
    """A library that caps versions forces downstream resolvers into conflicts (e.g. with linkml's rdflib>=7.6)."""
    capped = [str(r) for r in direct_requirements() if any(s.operator in UPPER_BOUND_OPERATORS for s in r.specifier)]
    assert not capped, f"Runtime dependencies must not be capped or pinned: {capped}"


def test_runtime_dependencies_are_not_dev_tools():
    dev_tools = {"pytest", "coverage", "tox", "black", "ruff", "codespell", "pre-commit", "griffe"}
    runtime = {canonicalize_name(r.name) for r in direct_requirements()}
    assert not runtime & dev_tools


def imported_top_level_modules() -> set[str]:
    names = set()
    for path in (ROOT / "pyshex").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                names |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def imported_distributions() -> set[str]:
    import sys

    module_to_dists = metadata.packages_distributions()
    dists = set()
    for module in imported_top_level_modules() - set(sys.stdlib_module_names) - {"pyshex"}:
        found = module_to_dists.get(module)
        assert found, f"pyshex imports {module!r}, which no installed distribution provides"
        dists |= {canonicalize_name(d) for d in found}
    return dists


def test_imports_are_declared_dependencies():
    declared = {canonicalize_name(r.name) for r in direct_requirements()}
    undeclared = imported_distributions() - declared
    assert undeclared <= IMPORTED_BUT_UNDECLARED, (
        f"pyshex imports {sorted(undeclared - IMPORTED_BUT_UNDECLARED)} without declaring them in pyproject.toml"
    )
    fixed = IMPORTED_BUT_UNDECLARED - undeclared
    assert not fixed, f"{sorted(fixed)} are now declared or unused; remove them from IMPORTED_BUT_UNDECLARED"


def test_declared_dependencies_are_used():
    declared = {canonicalize_name(r.name) for r in direct_requirements()}
    unused = declared - imported_distributions()
    assert unused <= DECLARED_BUT_NOT_IMPORTED, f"Declared but never imported: {sorted(unused)}"
    fixed = DECLARED_BUT_NOT_IMPORTED - unused
    assert not fixed, f"{sorted(fixed)} are now imported or removed; update DECLARED_BUT_NOT_IMPORTED"


def test_lockfile_declares_same_requirements_as_pyproject():
    locked = {canonicalize_name(p["name"]): p for p in lockfile()["package"]}["pyshex"]["metadata"]["requires-dist"]
    locked_names = {canonicalize_name(r["name"]) for r in locked}
    assert locked_names == {canonicalize_name(r.name) for r in direct_requirements()}, "run `uv lock`"


def test_no_dependency_on_heavy_frameworks():
    """Belt and braces: names that must never appear in the runtime closure."""
    heavy = re.compile(r"^(numpy|pandas|scipy|torch|tensorflow|jax|pyarrow|polars|matplotlib|ipython|jupyter.*|"
                       r"notebook|pydantic|sqlalchemy|django|flask|fastapi|lxml|networkx|openai|anthropic)$")
    assert not [n for n in locked_runtime_closure() if heavy.match(n)]
