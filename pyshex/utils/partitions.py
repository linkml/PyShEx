"""
Partition utilities -
taken from `Stack Overflow <https://stackoverflow.com/questions/19368375/set-partitions-in-python>`_
"""
from itertools import permutations
from typing import Iterator

from pyshex.shapemap_structure_and_language.p1_notation_and_terminology import RDFGraph


def algorithm_u(ns, m):
    """
    taken from `Stack Overflow <https://codereview.stackexchange.com/questions/1526/finding-all-k-subset-partitions>`_

    """
    def visit(nv, av):
        ps = [[] for _ in range(m)]
        for jv in range(nv):
            ps[av[jv + 1]].append(ns[jv])
        return ps

    def f(mu, nu, sigma, n, a):
        if mu == 2:
            yield visit(n, a)
        else:
            for v in f(mu - 1, nu - 1, (mu + sigma) % 2, n, a):
                yield v
        if nu == mu + 1:
            a[mu] = mu - 1
            yield visit(n, a)
            while a[nu] > 0:
                a[nu] = a[nu] - 1
                yield visit(n, a)
        elif nu > mu + 1:
            if (mu + sigma) % 2 == 1:
                a[nu - 1] = mu - 1
            else:
                a[mu] = mu - 1
            if (a[nu] + sigma) % 2 == 1:
                for v in b(mu, nu - 1, 0, n, a):
                    yield v
            else:
                for v in f(mu, nu - 1, 0, n, a):
                    yield v
            while a[nu] > 0:
                a[nu] = a[nu] - 1
                if (a[nu] + sigma) % 2 == 1:
                    for v in b(mu, nu - 1, 0, n, a):
                        yield v
                else:
                    for v in f(mu, nu - 1, 0, n, a):
                        yield v

    def b(mu, nu, sigma, n, a):
        if nu == mu + 1:
            while a[nu] < mu - 1:
                yield visit(n, a)
                a[nu] = a[nu] + 1
            yield visit(n, a)
            a[mu] = 0
        elif nu > mu + 1:
            if (a[nu] + sigma) % 2 == 1:
                for v in f(mu, nu - 1, 0, n, a):
                    yield v
            else:
                for v in b(mu, nu - 1, 0, n, a):
                    yield v
            while a[nu] < mu - 1:
                a[nu] = a[nu] + 1
                if (a[nu] + sigma) % 2 == 1:
                    for v in f(mu, nu - 1, 0, n, a):
                        yield v
                else:
                    for v in b(mu, nu - 1, 0, n, a):
                        yield v
            if (mu + sigma) % 2 == 1:
                a[nu - 1] = 0
            else:
                a[mu] = 0
        if mu == 2:
            yield visit(n, a)
        else:
            for v in b(mu - 1, nu - 1, (mu + sigma) % 2, n, a):
                yield v

    ng = len(ns)
    ag = [0] * (ng + 1)
    for j in range(1, m + 1):
        ag[ng - m + j] = j - 1
    return f(m, ng, 0, ng, ag) if m > 1 else [[ns]]


def integer_partition(size: int, nparts: int) -> Iterator[list[list[int]]]:
    """ Partition a list of integers into a list of partitions """
    for part in algorithm_u(range(size), nparts):
        yield part


def filtered_integer_partition(nelements: int, nparts: int) -> Iterator[tuple[tuple[int]]]:
    seen: set[tuple[tuple[int, ...], ...]] = set()

    # Start with the entire set
    if nelements == 0:
        yield tuple(tuple() for _ in range(nparts))
    else:
        for npart in range(min(nelements, nparts), 0, -1):
            if npart == 1:
                t1 = tuple(range(nelements))
                t2 = [() for _ in range(nparts - 1)]
                total = tuple([t1] + t2)
                for permutation in permutations(total):
                    pt = tuple(permutation)
                    if pt not in seen:
                        seen.add(pt)
                        yield pt
            else:
                for int_partition in integer_partition(nelements, npart):
                    t1 = [tuple(e) for e in int_partition]
                    t2 = [() for _ in range(nparts - npart)]
                    total = tuple(t1 + t2)
                    for permutation in permutations(total):
                        for permutation in permutations(total):
                            pt = tuple(permutation)
                            if pt not in seen:
                                seen.add(pt)
                                yield pt


    # def strip_empty_members(partition: list[list[int]]) -> tuple[tuple[int, ...], ...]:
    #     return tuple(tuple([p for p in part if p < nelements]) for part in partition)
    #
    # if nelements == 0:
    #     yield tuple(tuple() for _ in range(nparts))
    # else:
    #     for int_partition in integer_partition(nelements + nparts - 1, nparts):
    #         for permutation in permutations(int_partition):
    #             stripped_perm = strip_empty_members(permutation)
    #             if stripped_perm not in seen:
    #                 seen.add(stripped_perm)
    #                 yield stripped_perm


def partition_t(T: RDFGraph, nparts: int) -> Iterator[tuple[RDFGraph, ...]]:
    """
    Partition T into all possible partitions of T of size nparts
    :param T: Set of RDF triples to be partitioned
    :param nparts: number of partitions (e.g. 2 means return all possible 2 set partitions
    :return: Iterator that returns partitions

    We don't actually partition the triples directly -- instead, we partition a set of integers that
    reference elements in the (ordered) set and return those
    """
    def partition_map(partition: list[list[int]]) -> tuple[RDFGraph, ...]:
        rval: list[RDFGraph, ...] = []
        for part in partition:
            if len(part) == 1 and part[0] >= t_list_len:
                rval.append(RDFGraph())
            else:
                rval.append(RDFGraph([t_list[e] for e in part if e < t_list_len]))
        return tuple(rval)

    t_list = sorted(list(T))      # Sorted not strictly necessary, but aids testing
    t_list_len = len(t_list)
    return map(lambda partition: partition_map(partition), filtered_integer_partition(t_list_len, nparts))


def partition_2(T: RDFGraph) -> list[tuple[RDFGraph, RDFGraph]]:
    """
    Partition T into all possible combinations of two subsets
    :param T: RDF Graph to partition
    :return:
    """
    for p in partition_t(T, 2):
        yield p
