// Drive shex.js's extension-map for the differential tests (test_shexjs_differential.py).
//
//   node shexjs_driver.js <extension-map dir> bind <schema.shex> <data.ttl> <focus> [<start>]
//       validates <focus> and prints the Map extension's bindings as JSON; <focus> "ROOT" means
//       the data's one subject that is nobody's object (a blank node the caller cannot name)
//   node shexjs_driver.js <extension-map dir> materialize <schema.shex> <bindings.json> <root> [<start>] [<statics.json>]
//       runs ThreadedMaterializer and prints the result as N-Triples
//
// <focus>/<root> are IRIs or _:labels; <start> is a shape IRI (relative ones resolve against the
// schema base, as PyShEx's manifests write them) or "START".
"use strict";
const [X, mode, schemaPath, dataPath, node, startArg, staticsPath] = process.argv.slice(2);
const req = m => require(require.resolve(m, {paths: [X]}));
const Fs = require("fs");
const ShExParser = req("@shexjs/parser"), N3 = req("n3"), ShExUtil = req("@shexjs/util"), ShExTerm = req("@shexjs/term");
const {ShExValidator, resultMapToShapeExprTest} = req("@shexjs/validator");
const {ctor: RdfJsDb} = req("@shexjs/neighborhood-rdfjs");
const Mapper = require(X)({rdfjs: N3, Validator: ShExValidator});
const {ThreadedMaterializer} = require(X + "/lib/ThreadedMaterializer");

const TURTLE_BASE = "http://a.example/turtle/";           // what test_examples.py parses data with
const SCHEMA_BASE = "http://a.example/schema/";
const schema = ShExParser.construct(SCHEMA_BASE, {}, {index: true}).parse(Fs.readFileSync(schemaPath, "utf8"));
const start = !startArg || startArg === "START" ? ShExValidator.Start : new URL(startArg, SCHEMA_BASE).href;

if (mode === "bind") {
  const store = new N3.Store();
  store.addQuads(new N3.Parser({baseIRI: TURTLE_BASE, format: "text/turtle"}).parse(Fs.readFileSync(dataPath, "utf8")));
  const validator = new ShExValidator(schema, RdfJsDb(store), {noCache: true});
  Mapper.register(validator, {ShExTerm, ShExUtil});
  let focus = node.startsWith("_:") ? N3.DataFactory.blankNode(node.slice(2)) : node;
  if (node === "ROOT") {
    const objects = new Set(store.getQuads(null, null, null, null).map(q => q.object.id));
    const roots = [...new Set(store.getQuads(null, null, null, null).map(q => q.subject).filter(s => !objects.has(s.id)))];
    if (roots.length !== 1) { console.error("expected one root, found " + roots.length); process.exit(2); }
    focus = roots[0].termType === "BlankNode" ? "_:" + roots[0].value : roots[0].value;  // the validator wants JSON-LD-style terms
  }
  const res = resultMapToShapeExprTest(validator.validateShapeMap([{node: focus, shape: start}]));
  if (res.errors) { console.error(JSON.stringify(res.errors, null, 1)); process.exit(2); }
  process.stdout.write(JSON.stringify(ShExUtil.valToExtension(res, Mapper.url)) + "\n");
} else if (mode === "materialize") {
  const bindings = JSON.parse(Fs.readFileSync(dataPath, "utf8"));
  const staticVars = staticsPath ? JSON.parse(Fs.readFileSync(staticsPath, "utf8")) : {};
  const m = new ThreadedMaterializer(schema, {staticVars});
  const quads = m.materialize(bindings, node, start === ShExValidator.Start ? undefined : start);
  const writer = new N3.Writer({format: "N-Triples"});
  quads.forEach(q => writer.addQuad(q));
  writer.end((err, out) => { if (err) throw err; process.stdout.write(out); });
} else {
  console.error("mode must be bind or materialize"); process.exit(1);
}
