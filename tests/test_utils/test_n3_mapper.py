from pathlib import Path

from rdflib import Graph, BNode

from pyshex.utils.n3_mapper import N3Mapper


def test_basics():
    base_dir = Path(__file__).resolve().parent
    source_dir = base_dir / "source"
    target_dir = base_dir / "object"
    target_dir.mkdir(exist_ok=True)

    new_files = False

    for fpath in source_dir.iterdir():
        if not fpath.is_file():
            continue

        g = Graph()
        g.parse(str(fpath), format="turtle")

        mapper = N3Mapper(g.namespace_manager)

        result = "\n".join(
            mapper.n3(t)
            for t in sorted(
                g,
                key=lambda t: (1, t) if isinstance(t[0], BNode) else (0, t),
            )
        )

        tpath = target_dir / fpath.name

        if not tpath.exists():
            print(f"Creating: {tpath}")
            tpath.write_text(result)
            new_files = True

        assert tpath.read_text() == result

    assert not new_files, "New test files created - rerun tests"