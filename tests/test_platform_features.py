"""platformFeatures: la app de negocios oculta QvaPay/USDT/KYC si están apagados."""

import asyncio
import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.app_config.queries as app_config_queries
from schema.schema import schema

QUERY = "{ platformFeatures { qvapayEnabled usdtEnabled cashKycEnabled } }"


def _features():
    result = asyncio.run(schema.execute(QUERY))
    assert result.errors is None
    return result.data["platformFeatures"]


def test_everything_off_by_default(monkeypatch):
    monkeypatch.setattr(app_config_queries, "ENABLED_PAYMENT_METHOD_TYPES", {"cash", "transfer"})
    monkeypatch.setattr(app_config_queries, "ENABLED_DIGITAL_PROVIDER_CODES", set())
    monkeypatch.setattr(app_config_queries.settings, "cash_kyc_feature_enabled", False)
    assert _features() == {"qvapayEnabled": False, "usdtEnabled": False, "cashKycEnabled": False}


def test_method_needs_both_the_method_and_the_provider(monkeypatch):
    monkeypatch.setattr(app_config_queries, "ENABLED_PAYMENT_METHOD_TYPES", {"qvapay", "usdt"})
    monkeypatch.setattr(app_config_queries, "ENABLED_DIGITAL_PROVIDER_CODES", {"qvapay"})
    monkeypatch.setattr(app_config_queries.settings, "cash_kyc_feature_enabled", True)
    assert _features() == {"qvapayEnabled": True, "usdtEnabled": False, "cashKycEnabled": True}
