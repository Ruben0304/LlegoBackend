"""Diversity-aware re-ranking (MMR-lite) for recommendation results.

Pure semantic nearest-neighbours tend to cluster: many near-duplicate products,
or several items from the same branch dominating the list. This penalises
repeated keys (branch / category) so the final list stays relevant but varied —
without needing the candidate vectors (metadata diversity instead of vector MMR,
which is far cheaper at request time).
"""
from typing import Any, Callable, List, Optional, TypeVar

T = TypeVar("T")


def diversify(
    items: List[T],
    score_fn: Callable[[T], float],
    key_fns: List[Callable[[T], Any]],
    penalty: float = 0.3,
    limit: Optional[int] = None,
) -> List[T]:
    """Greedy MMR-lite re-rank.

    At each step pick the item with the highest *adjusted* score, where the
    adjusted score subtracts ``penalty`` for every already-selected item that
    shares a key (e.g. same branchId or categoryId). Relevance still dominates,
    but repeats get pushed down so the list interleaves across branches and
    categories.

    Args:
        items: candidates to re-rank.
        score_fn: relevance score for an item (higher = better).
        key_fns: one or more functions extracting a diversity key per dimension
            (e.g. branchId, categoryId). A None key never incurs a penalty.
        penalty: how hard to push down repeats of the same key.
        limit: stop after selecting this many (defaults to all items).

    Complexity is O(n^2); intended for the small candidate sets (tens of items)
    that recommendation queries return.
    """
    remaining = list(items)
    selected: List[T] = []
    seen_counts: List[dict] = [dict() for _ in key_fns]

    target = limit if limit is not None else len(remaining)
    while remaining and len(selected) < target:
        best_idx = 0
        best_adj = None
        for idx, item in enumerate(remaining):
            adj = score_fn(item)
            for dim, key_fn in enumerate(key_fns):
                key = key_fn(item)
                if key is not None:
                    adj -= penalty * seen_counts[dim].get(key, 0)
            if best_adj is None or adj > best_adj:
                best_adj = adj
                best_idx = idx

        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        for dim, key_fn in enumerate(key_fns):
            key = key_fn(chosen)
            if key is not None:
                seen_counts[dim][key] = seen_counts[dim].get(key, 0) + 1

    return selected
