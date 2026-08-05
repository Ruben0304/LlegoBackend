"""Unit tests for services.orders_utils.compute_fee_recommendation.

This tests only the pure statistics function. The MongoDB aggregation that
feeds it (OrderRepository.get_recent_delivery_fees) filters/sorts/limits
real order documents and isn't covered here — this project has no live or
mocked MongoDB test layer (see tests/test_cash_kyc_integration.py and
tests/test_branch_delivery_request_concurrency.py for the established
convention this follows instead).
"""

import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from services.orders_utils import compute_fee_recommendation


def test_zero_records_returns_no_recommendation_not_zero():
    result = compute_fee_recommendation([])
    assert result == {
        "recommendedFee": None,
        "sampleSize": 0,
        "confidence": "insufficient_data",
    }


def test_one_record_uses_that_value_with_low_confidence():
    result = compute_fee_recommendation([5.0])
    assert result["recommendedFee"] == 5.0
    assert result["sampleSize"] == 1
    assert result["confidence"] == "low"


def test_two_records_averages_them_with_low_confidence():
    result = compute_fee_recommendation([4.0, 6.0])
    assert result["recommendedFee"] == 5.0
    assert result["sampleSize"] == 2
    assert result["confidence"] == "low"


def test_repeated_values_return_that_value():
    result = compute_fee_recommendation([5.0, 5.0, 5.0, 5.0])
    assert result["recommendedFee"] == 5.0
    assert result["sampleSize"] == 4


def test_dispersed_values_return_true_median():
    # sorted: 1, 3, 5, 7, 9 -> median 5
    result = compute_fee_recommendation([9.0, 1.0, 5.0, 3.0, 7.0])
    assert result["recommendedFee"] == 5.0


def test_extreme_outlier_does_not_drag_the_recommendation():
    fees = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 50.0]
    result = compute_fee_recommendation(fees)
    # Mean would be ~10.6 — the median must stay anchored near the real cluster.
    assert result["recommendedFee"] == 5.0


def test_recency_is_the_callers_responsibility_not_reordered_here():
    """The function trusts the input order/selection — it's the caller
    (OrderRepository.get_recent_delivery_fees, sorted by completedAt desc
    and $limit-ed) that encodes "recent". This just proves the function
    doesn't silently drop or reorder entries in a way that would break that
    contract — every value passed in is used."""
    fees = [10.0, 10.0, 10.0, 20.0, 20.0]  # most-recent-first, as the caller would pass
    result = compute_fee_recommendation(fees)
    assert result["sampleSize"] == 5
    assert result["recommendedFee"] == 10.0  # median of the full set


def test_invalid_and_negative_values_are_excluded():
    fees = [5.0, -3.0, 0.0, None, 7.0]
    result = compute_fee_recommendation(fees)
    assert result["sampleSize"] == 2  # only 5.0 and 7.0 survive
    assert result["recommendedFee"] == 6.0


def test_all_invalid_values_is_same_as_empty():
    result = compute_fee_recommendation([-1.0, 0.0, -5.0])
    assert result["confidence"] == "insufficient_data"
    assert result["recommendedFee"] is None


def test_rounding_to_two_decimals():
    result = compute_fee_recommendation([1.0, 2.0, 2.0])  # median = 2.0, no rounding needed
    assert result["recommendedFee"] == 2.0

    result = compute_fee_recommendation([1.111, 2.222])  # even count -> averaged
    assert result["recommendedFee"] == round((1.111 + 2.222) / 2, 2)


def test_confidence_scales_with_sample_size():
    assert compute_fee_recommendation([5.0] * 2)["confidence"] == "low"
    assert compute_fee_recommendation([5.0] * 3)["confidence"] == "medium"
    assert compute_fee_recommendation([5.0] * 7)["confidence"] == "medium"
    assert compute_fee_recommendation([5.0] * 8)["confidence"] == "high"
