from rdflib import Graph, URIRef, BNode, RDF


def format_collection(g: Graph, subj: URIRef | BNode, max_entries: int = None, nentries: int = 0) -> list[str] | None:
    """
    Return the turtle representation of subj as a collection

    :param g: Graph containing subj
    :param subj: subject of list
    :param max_entries: maximum number of list elements to return, None means all
    :param nentries: used for recursion

    :return: list of formatted entries if subj heads a well formed collection else None
    """
    if subj == RDF.nil:
        return [')']
    if max_entries is not None and nentries >= max_entries:
        return ['  ...', ')']
    cadr = cdr = None
    for p, o in g.predicate_objects(subj):
        if p == RDF.first and cadr is None:
            cadr = o
        elif p == RDF.rest and cdr is None:
            cdr = o
        else:
            return None
    # technically this can't happen but it doesn't hurt to address it
    if cadr == RDF.nil and cdr is None:
        return []
    elif cadr is not None and cdr is not None:
        return [(' ' if nentries else '(') + cadr.n3(g.namespace_manager)] + format_collection(g, cdr, max_entries,
                                                                                                   nentries+1)
    else:
        return None

