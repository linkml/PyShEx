import pytest

from rdflib import Graph, RDF, Literal, XSD

from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph, RDFTriple
from pyshex.utils.partitions import algorithm_u, partition_t, partition_2, filtered_integer_partition, integer_partition
from tests.utils.setup_test import gen_rdf, rdf_header, EX


def test_algorithm_u() -> None:
    def organize(parts) -> str:
        return '; '.join('|'.join(''.join(str(e) for e in loe) for loe in part) for part in parts)

    x = list("abcde")
    permutations = [organize(algorithm_u(x, n)) for n in range(1, len(x) + 1)]
    assert permutations == [
        'abcde',
        'abcd|e; acd|be; ad|bce; abd|ce; ab|cde; a|bcde; ac|bde; abc|de; abce|d; '
        'ace|bd; ae|bcd; abe|cd; abde|c; ade|bc; acde|b',
        'abc|d|e; ab|cd|e; a|bcd|e; ac|bd|e; acd|b|e; ad|bc|e; abd|c|e; ab|c|de; '
        'a|bc|de; ac|b|de; a|b|cde; a|bd|ce; ad|b|ce; ad|be|c; a|bde|c; a|be|cd; '
        'ac|be|d; a|bce|d; ab|ce|d; abe|c|d; ae|bc|d; ace|b|d; ae|b|cd; ae|bd|c; '
        'ade|b|c',
        'ab|c|d|e; a|bc|d|e; ac|b|d|e; a|b|cd|e; a|bd|c|e; ad|b|c|e; a|b|c|de; '
        'a|b|ce|d; a|be|c|d; ae|b|c|d',
        'a|b|c|d|e',
    ]
    assert list(algorithm_u([1, 2], 2)) == [[[1], [2]]]


def test_filtered_integer_partition() -> None:
    assert list(filtered_integer_partition(0, 2)) == [((), ())]
    assert list(filtered_integer_partition(1, 2)) == [((0,), ()), ((), (0,))]
    assert list(filtered_integer_partition(2, 2)) == [
        ((0,), (1,)), ((1,), (0,)), ((0, 1), ()), ((), (0, 1)),
    ]
    assert list(filtered_integer_partition(3, 2)) == [
        ((0, 1), (2,)),
        ((2,), (0, 1)),
        ((0,), (1, 2)),
        ((1, 2), (0,)),
        ((0, 2), (1,)),
        ((1,), (0, 2)),
        ((0, 1, 2), ()),
        ((), (0, 1, 2)),
    ]
    assert list(filtered_integer_partition(0, 3)) == [((), (), ())]
    assert list(filtered_integer_partition(1, 3)) == [
        ((0,), (), ()), ((), (0,), ()), ((), (), (0,)),
    ]
    assert list(filtered_integer_partition(2, 3)) == [
        ((0,), (1,), ()),
        ((0,), (), (1,)),
        ((1,), (0,), ()),
        ((1,), (), (0,)),
        ((), (0,), (1,)),
        ((), (1,), (0,)),
        ((0, 1), (), ()),
        ((), (0, 1), ()),
        ((), (), (0, 1)),
    ]
    assert list(filtered_integer_partition(3, 3)) == [
        ((0,), (1,), (2,)),
        ((0,), (2,), (1,)),
        ((1,), (0,), (2,)),
        ((1,), (2,), (0,)),
        ((2,), (0,), (1,)),
        ((2,), (1,), (0,)),
        ((0, 1), (2,), ()),
        ((0, 1), (), (2,)),
        ((2,), (0, 1), ()),
        ((2,), (), (0, 1)),
        ((), (0, 1), (2,)),
        ((), (2,), (0, 1)),
        ((0,), (1, 2), ()),
        ((0,), (), (1, 2)),
        ((1, 2), (0,), ()),
        ((1, 2), (), (0,)),
        ((), (0,), (1, 2)),
        ((), (1, 2), (0,)),
        ((0, 2), (1,), ()),
        ((0, 2), (), (1,)),
        ((1,), (0, 2), ()),
        ((1,), (), (0, 2)),
        ((), (0, 2), (1,)),
        ((), (1,), (0, 2)),
        ((0, 1, 2), (), ()),
        ((), (0, 1, 2), ()),
        ((), (), (0, 1, 2)),
    ]
    assert list(filtered_integer_partition(4, 3)) == [
        ((0, 1), (2,), (3,)),
        ((0, 1), (3,), (2,)),
        ((2,), (0, 1), (3,)),
        ((2,), (3,), (0, 1)),
        ((3,), (0, 1), (2,)),
        ((3,), (2,), (0, 1)),
        ((0,), (1, 2), (3,)),
        ((0,), (3,), (1, 2)),
        ((1, 2), (0,), (3,)),
        ((1, 2), (3,), (0,)),
        ((3,), (0,), (1, 2)),
        ((3,), (1, 2), (0,)),
        ((0, 2), (1,), (3,)),
        ((0, 2), (3,), (1,)),
        ((1,), (0, 2), (3,)),
        ((1,), (3,), (0, 2)),
        ((3,), (0, 2), (1,)),
        ((3,), (1,), (0, 2)),
        ((0,), (1,), (2, 3)),
        ((0,), (2, 3), (1,)),
        ((1,), (0,), (2, 3)),
        ((1,), (2, 3), (0,)),
        ((2, 3), (0,), (1,)),
        ((2, 3), (1,), (0,)),
        ((0,), (1, 3), (2,)),
        ((0,), (2,), (1, 3)),
        ((1, 3), (0,), (2,)),
        ((1, 3), (2,), (0,)),
        ((2,), (0,), (1, 3)),
        ((2,), (1, 3), (0,)),
        ((0, 3), (1,), (2,)),
        ((0, 3), (2,), (1,)),
        ((1,), (0, 3), (2,)),
        ((1,), (2,), (0, 3)),
        ((2,), (0, 3), (1,)),
        ((2,), (1,), (0, 3)),
        ((0, 1, 2), (3,), ()),
        ((0, 1, 2), (), (3,)),
        ((3,), (0, 1, 2), ()),
        ((3,), (), (0, 1, 2)),
        ((), (0, 1, 2), (3,)),
        ((), (3,), (0, 1, 2)),
        ((0, 2), (1, 3), ()),
        ((0, 2), (), (1, 3)),
        ((1, 3), (0, 2), ()),
        ((1, 3), (), (0, 2)),
        ((), (0, 2), (1, 3)),
        ((), (1, 3), (0, 2)),
        ((0,), (1, 2, 3), ()),
        ((0,), (), (1, 2, 3)),
        ((1, 2, 3), (0,), ()),
        ((1, 2, 3), (), (0,)),
        ((), (0,), (1, 2, 3)),
        ((), (1, 2, 3), (0,)),
        ((0, 1), (2, 3), ()),
        ((0, 1), (), (2, 3)),
        ((2, 3), (0, 1), ()),
        ((2, 3), (), (0, 1)),
        ((), (0, 1), (2, 3)),
        ((), (2, 3), (0, 1)),
        ((0, 1, 3), (2,), ()),
        ((0, 1, 3), (), (2,)),
        ((2,), (0, 1, 3), ()),
        ((2,), (), (0, 1, 3)),
        ((), (0, 1, 3), (2,)),
        ((), (2,), (0, 1, 3)),
        ((0, 3), (1, 2), ()),
        ((0, 3), (), (1, 2)),
        ((1, 2), (0, 3), ()),
        ((1, 2), (), (0, 3)),
        ((), (0, 3), (1, 2)),
        ((), (1, 2), (0, 3)),
        ((0, 2, 3), (1,), ()),
        ((0, 2, 3), (), (1,)),
        ((1,), (0, 2, 3), ()),
        ((1,), (), (0, 2, 3)),
        ((), (0, 2, 3), (1,)),
        ((), (1,), (0, 2, 3)),
        ((0, 1, 2, 3), (), ()),
        ((), (0, 1, 2, 3), ()),
        ((), (), (0, 1, 2, 3)),
    ]


def test_large_integer_partition() -> None:
    x = integer_partition(25, 20)
    [next(x) for _ in range(100)]
    assert next(x) == [
        [0, 3], [1, 2, 4], [5, 6, 7],
        [8], [9], [10], [11], [12], [13], [14],
        [15], [16], [17], [18], [19], [20],
        [21], [22], [23], [24],
    ]


def test_large_filtered_integer() -> None:
    """Generators must work all the way through without forcing full realisation."""
    x = filtered_integer_partition(25, 20)
    [next(x) for _ in range(100)]
    assert next(x) == (
        (0, 1, 2, 3, 4, 5),
        (6,), (7,), (8,), (9,), (10,),
        (11,), (12,), (13,), (14,), (15,),
        (16,), (17,), (18,), (19,), (24,),
        (20,), (23,), (21,), (22,),
    )


def test_partition_t() -> None:
    t1 = RDFTriple((EX.Alice, EX.shoeSize, Literal(30, datatype=XSD.integer)))
    t2 = RDFTriple((EX.Alice, RDF.type, EX.Teacher))
    g = Graph()
    g0 = RDFGraph(g)
    assert list(partition_t(g0, 2)) == [(RDFGraph(), RDFGraph())]
    g.add(t1)
    g1 = RDFGraph(g)
    assert list(partition_t(g1, 2)) == [(g1, g0), (g0, g1)]
    g.add(t2)
    g2 = RDFGraph(g)
    assert list(partition_t(g2, 2)) == [
        (g1, RDFGraph((t2,))),
        (RDFGraph((t2,)), g1),
        (g2, g0),
        (g0, g2),
    ]


def test_partition_2() -> None:
    g = Graph()
    grdf = RDFGraph(g)
    x11 = list(partition_2(grdf))
    assert x11 == [(RDFGraph(), RDFGraph())]
    assert list(partition_t(grdf, 2)) == x11

    triples = gen_rdf("""<Alice> ex:shoeSize "30"^^xsd:integer .""")
    g = Graph()
    g.parse(data=triples, format="turtle")
    grdf = RDFGraph(g)
    x21 = list(partition_2(grdf))
    assert len(x21) == 2
    assert list(partition_t(grdf, 2)) == x21

    triples = gen_rdf("""<Alice> ex:shoeSize "30"^^xsd:integer .
            <Alice> a ex:Teacher .""")
    g = Graph()
    g.parse(data=triples, format="turtle")
    assert len(list(partition_2(RDFGraph(g)))) == 4

    triples = gen_rdf("""<Alice> ex:shoeSize "30"^^xsd:integer .
                    <Alice> a ex:Teacher .
                    <Alice> a ex:Person .""")
    g = Graph()
    g.parse(data=triples, format="turtle")
    assert len(list(partition_2(RDFGraph(g)))) == 8

    triples = gen_rdf("""<Alice> ex:shoeSize "30"^^xsd:integer .
                    <Alice> a ex:Teacher .
                    <Alice> a ex:Person .
                    <Alice> a ex:Fool .""")
    g = Graph()
    g.parse(data=triples, format="turtle")
    assert len(list(partition_2(RDFGraph(g)))) == 16


@pytest.mark.skip(reason="test_large_partition performance issues -- needs optimization")
def test_large_partition() -> None:
    """Generators must work all the way through without forcing full realisation."""
    g = Graph()
    g.parse(data=rdf_header, format="turtle")
    for i in range(25):
        g.add((EX['s' + str(i)], RDF.type, EX.thing))
    rdfg = RDFGraph(g)

    part1 = partition_t(rdfg, 20)
    [next(part1) for _ in range(100)]
    assert [{str(list(e)[0]) for e in part} for part in next(part1)] == [
        {'http://schema.example/s0', 'http://schema.example/s1',
         'http://schema.example/s10', 'http://schema.example/s11',
         'http://schema.example/s12', 'http://schema.example/s13'},
        {'http://schema.example/s14'}, {'http://schema.example/s15'},
        {'http://schema.example/s16'}, {'http://schema.example/s17'},
        {'http://schema.example/s18'}, {'http://schema.example/s19'},
        {'http://schema.example/s2'},  {'http://schema.example/s20'},
        {'http://schema.example/s21'}, {'http://schema.example/s22'},
        {'http://schema.example/s23'}, {'http://schema.example/s24'},
        {'http://schema.example/s3'},  {'http://schema.example/s4'},
        {'http://schema.example/s9'},  {'http://schema.example/s5'},
        {'http://schema.example/s8'},  {'http://schema.example/s6'},
        {'http://schema.example/s7'},
    ]

    part2 = partition_t(rdfg, 1)
    assert sum(1 for _ in part2) == 1

    part3 = partition_t(rdfg, 25)
    assert sum(1 for _ in part3) == 1