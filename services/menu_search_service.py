"""Service for menu search by OCR text with quality ranking."""

from typing import Optional

from domain.models import BranchMenu
from repositories import branch_menus_repo
from services.menu_ocr_utils import query_terms, search_lines

MIN_QUERY_CHARS = 3
MAX_RESULTS = 20


async def search_menus(
    query: str, branch_ids: Optional[list[str]] = None, limit: int = 10
) -> list[dict]:
    """
    Search menus by OCR text.

    Args:
        query: Search query (normalized before tokenization)
        branch_ids: Optional list of branch IDs to search within
        limit: Maximum number of results to return (capped at 20)

    Returns:
        List of dicts with keys: 'menu' (BranchMenu), 'matches' (list of match dicts),
        'matchCount' (int)

    Raises:
        ValueError: If query has < 3 alphanumeric characters after normalization
    """
    if limit < 1:
        raise ValueError("El límite debe ser mayor que cero")
    limit = min(limit, MAX_RESULTS)
    query = query.strip()
    terms = query_terms(query)

    # Check if we have any trigrams (means >= 3 chars)
    if not terms["trigrams"]:
        raise ValueError("La búsqueda debe tener al menos 3 letras")

    # Get candidates from repo
    # Request more than limit to account for filtering
    fetch_limit = limit * 3
    candidates = await branch_menus_repo.find_candidates(
        terms["trigrams"], terms["tokens"], branch_ids, limit=fetch_limit
    )

    # Filter candidates: keep only those with matches
    results_with_matches = []
    for menu in candidates:
        matches = search_lines([dict(line) for line in menu.lines], query)
        if matches:
            results_with_matches.append(
                {"menu": menu, "matches": matches, "matchCount": len(matches)}
            )

    # Rank and return
    ranked = rank_results(results_with_matches, limit)
    return ranked


def rank_results(items: list[dict], limit: int = 10) -> list[dict]:
    """
    Rank search results by match count (descending).

    Stable sort respecting the order of input candidates, but prioritizing
    by matchCount.

    Args:
        items: List of dicts with 'menu', 'matches', 'matchCount'
        limit: Maximum results to return

    Returns:
        Sorted and limited list
    """
    # Sort by matchCount descending, preserving relative order of candidates
    # with same matchCount (stable sort)
    sorted_items = sorted(items, key=lambda x: x["matchCount"], reverse=True)
    return sorted_items[:limit]
