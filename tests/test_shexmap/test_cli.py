"""The shexmap command."""
import json
from pathlib import Path

from rdflib import Graph
from rdflib.compare import isomorphic

from pyshex.shexmap.cli import main

EX = Path(__file__).parent / "examples"


def expected(name: str) -> Graph:
    return Graph().parse(EX / name, format="turtle")


def test_bind_and_materialize(tmp_path, capsys):
    rc = main(["-i", str(EX / "BPfhir-instance.ttl"), "-s", str(EX / "BPfhir-schema.shex"), "-f", "<tag:BPfhir123>",
               "-t", str(EX / "BPdam-schema.shex"), "-r", "<tag:b0>", "-o", str(tmp_path / "out.ttl")])
    assert rc == 0
    assert isomorphic(Graph().parse(tmp_path / "out.ttl", format="turtle"), expected("BP-simple-out.ttl"))


def test_bindings_out_then_in(tmp_path, capsys):
    bindings = tmp_path / "b.json"
    assert main(["-i", str(EX / "BPfhir-instance.ttl"), "-s", str(EX / "BPfhir-schema.shex"),
                 "-f", "tag:BPfhir123", "-b", str(bindings)]) == 0
    assert json.loads(bindings.read_text(encoding="utf-8")) == json.loads((EX / "BP-simple-bindings.json").read_text(encoding="utf-8"))
    assert main(["-j", str(bindings), "-t", str(EX / "BPdam-schema.shex"), "-r", "<tag:b0>"]) == 0
    assert isomorphic(Graph().parse(data=capsys.readouterr().out, format="turtle"), expected("BP-simple-out.ttl"))


def test_nonconforming_focus_exits_1(capsys):
    rc = main(["-i", str(EX / "BPfhir-instance.ttl"), "-s", str(EX / "BPfhir-schema.shex"), "-f", "<tag:nope>",
               "-b", "-"])
    assert rc == 1
    assert "does not conform" in capsys.readouterr().err


PYEX = Path(__file__).parent / "pyshex-examples"


def test_ambiguous_input_warns_or_fails_with_strict(capsys):
    args = ["-i", str(PYEX / "bp-reading.ttl"), "-s", str(PYEX / "bp-ambiguous-schema.shex"),
            "-f", "<file://" + str((PYEX / "bp-reading.ttl").resolve().parent) + "/reading1>",
            "-t", str(PYEX / "bp-dam-schema.shex"), "-r", "<tag:bp1>"]
    assert main(args) == 0
    assert "matches in 2 ways" in capsys.readouterr().err
    assert main(args + ["--strict"]) == 1
    assert "2 ways" in capsys.readouterr().err
