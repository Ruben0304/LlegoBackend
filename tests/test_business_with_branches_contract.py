"""Contrato de getMyBusinessesWithBranches con la app de negocios.

La app de negocios (LlegoBussisnes) pide `predefinedDeliveryFee` en el fragment
`BusinessRoleFields on BusinessWithBranchesType`. Cuando el campo solo existía
en `BusinessType`, la query entera fallaba en validación y la app no podía
cargar sus negocios. Estos tests fijan el contrato del schema y que el
resolver lo rellena desde el modelo de dominio.
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from graphql import parse, validate

import repositories
import schema.businesses.queries as business_queries
from schema import schema as graphql_schema

USER_ID = "507f1f77bcf86cd799439014"
BUSINESS_ID = "507f1f77bcf86cd799439013"

# Copia del fragment que usa la app de negocios
# (composeApp/src/commonMain/graphql/fragments/BusinessFragments.graphql).
BUSINESS_APP_OPERATION = """
fragment BusinessRoleFields on BusinessWithBranchesType {
  id
  name
  ownerId
  avatar
  description
  tags
  globalRating
  isActive
  createdAt
  approvalStatus
  rejectionReason
  avatarUrl
  avatarUrlBaja
  avatarUrlAlta
  predefinedDeliveryFee
  isOwner
  role
}

query GetMyBusinessesWithBranches($jwt: String!) {
  getMyBusinessesWithBranches(jwt: $jwt) {
    ...BusinessRoleFields
  }
}
"""


def test_business_app_fragment_validates_against_schema():
    errors = validate(graphql_schema._schema, parse(BUSINESS_APP_OPERATION))
    assert errors == []


def test_resolver_populates_predefined_delivery_fee(monkeypatch):
    business = SimpleNamespace(
        id=BUSINESS_ID,
        name="Cafetería",
        ownerId=USER_ID,
        globalRating=4.5,
        avatar="avatars/a.jpg",
        description=None,
        tags=None,
        isActive=True,
        approvalStatus="approved",
        rejectionReason=None,
        approvedAt=None,
        rejectedAt=None,
        createdAt=datetime(2026, 1, 1),
        predefinedDeliveryFee=150.0,
    )

    def _auth(jwt, info):
        info.context["user_id"] = USER_ID

    monkeypatch.setattr(business_queries, "apply_optional_jwt", _auth)
    monkeypatch.setattr(
        business_queries.businesses_repo,
        "get_by_owner",
        AsyncMock(return_value=[business]),
    )
    monkeypatch.setattr(
        business_queries.branches_repo,
        "get_by_business_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        repositories.business_access_repo,
        "get_active_by_user",
        AsyncMock(return_value=[]),
    )

    info = SimpleNamespace(context={})
    result = asyncio.run(
        business_queries.BusinessQuery().get_my_businesses_with_branches(
            info=info, jwt="token"
        )
    )

    assert len(result) == 1
    assert result[0].predefinedDeliveryFee == 150.0
    assert result[0].role == "owner"
    assert result[0].isOwner is True
