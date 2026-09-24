# ShExMap tests

`examples/` is copied from shex.js's `@shexjs/extension-map` package
(https://github.com/shexjs/shex.js/tree/main/packages/extension-map/examples,
commit 58406c3bdd4fa79cc9b0f664ef7a689db040c07b, MIT licence, by Eric Prud'hommeaux).
Each `manifest.json` entry pairs an input schema and data with the bindings and
output graph shex.js produces; `test_examples.py` checks PyShEx against them.
