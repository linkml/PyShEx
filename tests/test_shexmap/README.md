# ShExMap tests

`examples/` is copied from shex.js's `@shexjs/extension-map` package
(https://github.com/shexjs/shex.js/tree/main/packages/extension-map/examples,
commit 58406c3bdd4fa79cc9b0f664ef7a689db040c07b, MIT licence, by Eric Prud'hommeaux).
Each `manifest.json` entry pairs an input schema and data with the bindings and
output graph shex.js produces; `test_examples.py` checks PyShEx against them.

`test_cardinality.py` covers cardinality above one: nothing caps how many values a
`*`/`+` binds or materializes; a nested schema maps to itself, sibling lists transpose,
a parent's binding can be read in every item, and a body reading from unrelated lists
is refused.

`test_values.py` covers the check of bound values against the output constraint's value
expression: retyping of plain literals, failure as an unbound variable, and conformance of
the output to its schema.

`test_examples.py` also checks the round-trip law on every example: materializing the
bindings with the *input* schema gives a graph that binds to the same bindings.

`test_shexjs_differential.py` runs every example through shex.js's `@shexjs/extension-map`
as well (`shexjs_driver.js`) and compares frames and graphs, when `SHEXJS_EXTENSION_MAP`
points at the package directory of a built shex.js checkout; skipped otherwise.

`test_keys.py` covers node identity: `%Map:{ id(v:a, v:b) %}` on a shape-valued constraint
keys its node, so equal keys merge (grouping by value, shared references); `id(@node)`
reuses the input node, so a schema maps a graph onto itself; unkeyed nodes are
reproducible and specific to the root.

`test_analysis.py` covers the static checks (`analyse`, `shexmap --check`): every example
pair and every schema against itself are coherent; unrelated lists, "which one?" reads,
unbound and unused variables, double binding sites and `id()` misuse are reported.

`test_roundtrip.py` covers the round-trip laws of a schema pair (a schema binds back what
it wrote from; BP <-> BP back and inverse in <-> inverse out recover their bindings, the BP
pair its graph) and the provenance each output triple carries.

`test_update.py` covers the triples a schema matched (`Bindings.matched`), the strong form
of the identity law, and updating a graph in place (`update`, `materialize(replace=True)`,
`shexmap --into`); `test_keys.py` also covers IRI templates in `id()`.

