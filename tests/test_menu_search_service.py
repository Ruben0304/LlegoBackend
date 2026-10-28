"""Tests for menu search service."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from services.menu_search_service import search_menus, rank_results
from services.menu_ocr_utils import QUALITY_MESSAGES_ES
from schema.branch_menus.types import menu_to_type


# Sample BranchMenu mock
def create_mock_menu(menu_id, branch_id, text_lines):
    """Create a mock BranchMenu for testing."""
    return type("BranchMenu", (), {
        "id": menu_id,
        "branchId": branch_id,
        "image": f"menus/{branch_id}/image.jpg",
        "isActive": True,
        "ocrStatus": "done",
        "ocrError": None,
        "quality": {
            "verdict": "good",
            "reasons": [],
            "tips": [],
        },
        "lines": text_lines,
        "tokens": [],
        "trigrams": [],
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    })()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, -2147483648])
async def test_search_rejects_nonpositive_limit_without_database_access(limit):
    with patch("repositories.branch_menus_repo.find_candidates", AsyncMock()) as find:
        with pytest.raises(ValueError, match="mayor que cero"):
            await search_menus("pizza", limit=limit)
    find.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_caps_large_limit_in_query_and_result():
    menu = create_mock_menu("menu", "branch", [{"text": "Pizza", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9}])
    with patch("repositories.branch_menus_repo.find_candidates", AsyncMock(return_value=[menu] * 80)) as find:
        results = await search_menus("pizza", limit=1000)
    assert find.await_args.kwargs["limit"] == 60
    assert len(results) == 20


@pytest.mark.asyncio
async def test_search_menus_query_too_short():
    """Test that queries with < 3 alphanumeric chars raise ValueError."""
    with pytest.raises(ValueError, match="debe tener al menos 3 letras"):
        await search_menus("ab")

    with pytest.raises(ValueError, match="debe tener al menos 3 letras"):
        await search_menus("  ")

    with pytest.raises(ValueError, match="debe tener al menos 3 letras"):
        await search_menus("")


@pytest.mark.asyncio
async def test_search_menus_finds_matches():
    """Test that search finds menus with matching text."""
    # Create mock menu with Pizza text
    menu = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza Margherita", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
            {"text": "Pasta Carbonara", "box": [[0, 0.2], [1, 0.2], [1, 0.3], [0, 0.3]], "conf": 0.85},
        ]
    )

    with patch("repositories.branch_menus_repo.find_candidates", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = [menu]

        results = await search_menus("pizza", limit=10)

        assert len(results) == 1
        assert results[0]["menu"] == menu
        assert results[0]["matchCount"] == 1
        assert len(results[0]["matches"]) == 1
        assert results[0]["matches"][0]["text"] == "Pizza"


@pytest.mark.asyncio
async def test_search_menus_with_typo():
    """Test fuzzy matching finds typos like 'piza' -> 'Pizza'."""
    menu = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza Margherita", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )

    with patch("repositories.branch_menus_repo.find_candidates", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = [menu]

        results = await search_menus("piza", limit=10)

        # Fuzzy matching should work for "piza" -> "pizza"
        assert len(results) == 1
        assert results[0]["matchCount"] >= 1


@pytest.mark.asyncio
async def test_search_menus_filters_no_matches():
    """Test that menus without matches are filtered out."""
    menu_with_pizza = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza Margherita", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )
    menu_no_match = create_mock_menu(
        "menu2",
        "branch2",
        [
            {"text": "Pasta Carbonara", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )

    with patch("repositories.branch_menus_repo.find_candidates", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = [menu_with_pizza, menu_no_match]

        results = await search_menus("pizza", limit=10)

        # Only menu_with_pizza should be returned
        assert len(results) == 1
        assert str(results[0]["menu"].branchId) == "branch1"


@pytest.mark.asyncio
async def test_search_menus_respects_limit():
    """Test that results are limited to the specified number."""
    menus = [
        create_mock_menu(
            f"menu{i}",
            f"branch{i}",
            [
                {
                    "text": "Pizza Margherita",
                    "box": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    "conf": 0.9
                }
            ]
        )
        for i in range(5)
    ]

    with patch("repositories.branch_menus_repo.find_candidates", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = menus

        results = await search_menus("pizza", limit=3)

        assert len(results) == 3


@pytest.mark.asyncio
async def test_search_menus_passes_branch_ids():
    """Test that branch_ids are passed to the repository."""
    menu = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )

    with patch("repositories.branch_menus_repo.find_candidates", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = [menu]

        branch_ids = ["branch1", "branch2"]
        await search_menus("pizza", branch_ids=branch_ids, limit=10)

        mock_find.assert_called_once()
        args, kwargs = mock_find.call_args
        # Check that branch_ids were passed
        assert kwargs.get("branch_ids") == branch_ids or args[2] == branch_ids


def test_rank_results_by_match_count():
    """Test that results are ranked by match count in descending order."""
    items = [
        {"menu": "m1", "matches": [1], "matchCount": 1},
        {"menu": "m2", "matches": [1, 2, 3], "matchCount": 3},
        {"menu": "m3", "matches": [1, 2], "matchCount": 2},
    ]

    ranked = rank_results(items)

    assert ranked[0]["matchCount"] == 3
    assert ranked[1]["matchCount"] == 2
    assert ranked[2]["matchCount"] == 1


def test_rank_results_respects_limit():
    """Test that rank_results respects the limit parameter."""
    items = [
        {"menu": f"m{i}", "matches": list(range(i+1)), "matchCount": i+1}
        for i in range(5)
    ]

    ranked = rank_results(items, limit=3)

    assert len(ranked) == 3
    assert ranked[0]["matchCount"] == 5
    assert ranked[1]["matchCount"] == 4
    assert ranked[2]["matchCount"] == 3


def test_menu_to_type_with_quality():
    """Test that menu_to_type builds quality messages correctly."""
    menu = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )
    menu.quality = {
        "verdict": "fair",
        "reasons": ["low_confidence"],
        "tips": ["dark", "blurry"],
    }

    menu_type = menu_to_type(menu)

    assert menu_type.quality is not None
    assert menu_type.quality.verdict == "fair"
    assert "low_confidence" in menu_type.quality.reasons
    assert "dark" in menu_type.quality.tips
    assert "blurry" in menu_type.quality.tips
    # Check that messages are built from QUALITY_MESSAGES_ES
    assert QUALITY_MESSAGES_ES["low_confidence"] in menu_type.quality.messages
    assert QUALITY_MESSAGES_ES["dark"] in menu_type.quality.messages
    assert QUALITY_MESSAGES_ES["blurry"] in menu_type.quality.messages


def test_menu_to_type_without_quality():
    """Test that menu_to_type handles None quality gracefully."""
    menu = create_mock_menu(
        "menu1",
        "branch1",
        [
            {"text": "Pizza", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "conf": 0.9},
        ]
    )
    menu.quality = None

    menu_type = menu_to_type(menu)

    assert menu_type.quality is None
    assert menu_type.ocrStatus == "done"


def test_schema_contains_search_menus():
    """Test that searchMenus query is in the schema."""
    from schema.schema import schema

    schema_str = schema.as_str()
    assert "searchMenus" in schema_str


def test_schema_contains_branch_menu_mutations():
    """Test that branch menu mutations are in the schema."""
    from schema.schema import schema

    schema_str = schema.as_str()
    assert "setBranchMenu" in schema_str
    assert "deleteBranchMenu" in schema_str
    assert "toggleBranchMenu" in schema_str
