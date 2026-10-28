"""Precision of the fuzzy menu search: typos match, word fragments do not.

The first version used rapidfuzz `partial_ratio_alignment` and highlighted short
fragments of unrelated words. These cases come from real menu photos.
"""

import pytest

from services.menu_ocr_utils import find_spans


@pytest.mark.parametrize(
    "text, query",
    [
        ("Chse", "cheeze"),  # 4-letter fragment of a 6-letter query
        ("SALE", "salad"),  # shares "sal" only
        ("fresh orange juice 4.00", "fries"),  # "fres" is a fragment of "fresh"
        ("Spaghetti Boloñesa", "salad"),
        ("Cerveza Cristal", "pizza"),
    ],
)
def test_fragments_of_other_words_do_not_match(text, query):
    assert find_spans(text, query) == []


@pytest.mark.parametrize(
    "text, query, expected",
    [
        ("Pizza Margarita", "piza", [(0, 5)]),  # missing letter
        ("Coffee 2.50", "cofee", [(0, 6)]),
        ("Chicken Wings", "chiken", [(0, 7)]),
        ("Club Sandwich 5.00", "sandwhich", [(5, 13)]),  # extra letter
        ("Cheese Pie", "cheeze", [(0, 6)]),  # substituted letter
    ],
)
def test_single_typos_match_the_whole_word(text, query, expected):
    assert find_spans(text, query) == expected


def test_multiword_typo_covers_both_words():
    assert find_spans("Pizza Margarita 8.50", "pizza margerita") == [(0, 15)]


def test_every_fuzzy_occurrence_in_a_line_is_reported():
    assert find_spans("Piza o Piza grande", "pizza") == [(0, 4), (7, 11)]


def test_fuzzy_is_only_used_when_there_is_no_exact_match():
    """An exact hit wins: the typo in the same line is not reported alongside it."""
    assert find_spans("Pizza o Piza grande", "pizza") == [(0, 5)]


def test_exact_match_still_finds_words_glued_by_the_ocr():
    """The OCR often drops spaces and punctuation: exact search is substring based."""
    assert find_spans("norm.PIZZA", "pizza") == [(5, 10)]
    assert find_spans("horsham.coffee roaster,downsviewmilk", "milk") == [(32, 36)]


def test_queries_shorter_than_four_chars_never_use_fuzzy():
    assert find_spans("Pizza", "pzz") == []
