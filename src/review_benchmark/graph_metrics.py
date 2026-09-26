import itertools
import math

def ratio(a, b):
    return a / b if b else None

def counts(pred, gold):
    p, g = set(pred), set(gold)
    tp, fp, fn = len(p & g), len(p - g), len(g - p)
    return dict(tp=tp, fp=fp, fn=fn, precision=ratio(tp, tp+fp),
                recall=ratio(tp, tp+fn), f1=ratio(2*tp, 2*tp+fp+fn))

def pair(a, b):
    if type(a) is not int or type(b) is not int or a < 0 or b < 0 or a == b:
        raise ValueError('An edge requires distinct nonnegative integer Solid IDs')
    return tuple(sorted((a, b)))

def canonical(name, aliases):
    # Only independently declared equivalence classes; never guess from spelling.
    return aliases.get(name, name)

def graph_cost(p, g, mapping, aliases):
    pn = {n['id']: canonical(n['label'], aliases) for n in p['nodes']}
    gn = {n['id']: canonical(n['label'], aliases) for n in g['nodes']}
    pe = {pair(e['a'], e['b']): set(e['types']) for e in p['edges']}
    ge = {pair(e['a'], e['b']): set(e['types']) for e in g['edges']}
    cost = len(pn)+len(gn)-2*len(mapping)
    cost += sum(pn[a] != gn[b] for a, b in mapping.items())
    used = set()
    for (a, b), labels in pe.items():
        target = pair(mapping[a], mapping[b]) if a in mapping and b in mapping else None
        if target in ge:
            # Relabeling may be more expensive than deleting and reinserting
            # the whole attributed edge (two unit-cost operations).
            cost += min(len(labels ^ ge[target]), 2); used.add(target)
        else:
            cost += 1
    return cost + len(ge)-len(used)

def ged(p, g, aliases=None, exact_limit=6):
    """Unrestricted undirected labeled GED; small graphs exhaustive, else upper bound.

    Unit node insertion/deletion/relabel, unit whole-edge insertion/deletion,
    unit per-type-label insertion/deletion on retained edges. Dimensions excluded.
    Exact search includes PARTIAL injective assignments, not just permutations.
    """
    aliases = aliases or {}
    a, b = [n['id'] for n in p['nodes']], [n['id'] for n in g['nodes']]
    identity = {x: x for x in a if x in b}
    best = min(graph_cost(p, g, {}, aliases), graph_cost(p, g, identity, aliases))
    if best == 0:
        return dict(value=0, upper_bound=0, status='exact_zero_witness')
    if max(len(a), len(b)) > exact_limit:
        return dict(value=None, upper_bound=best, status='upper_bound_only_size_limit')
    for k in range(min(len(a), len(b))+1):
        for aa in itertools.combinations(a, k):
            for bb in itertools.permutations(b, k):
                best = min(best, graph_cost(p, g, dict(zip(aa, bb)), aliases))
    return dict(value=best, upper_bound=best, status='exact_exhaustive')
