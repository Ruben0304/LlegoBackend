"""Canonical Qdrant payload builders.

Single source of truth for the payload stored alongside each entity's vector so
that every writer (repositories, indexing service, backfill scripts) stays
consistent.

Enriching the payload is what unlocks **server-side filtering** in Qdrant
(by branch, category, availability, geo, business, ...) instead of fetching a
larger candidate set and post-filtering it in Python. Building a payload does
NOT require Gemini or Qdrant — it's pure attribute access, so it is cheap to
call on every write and inside `set_payload` (payload-only) updates.
"""
from typing import Any, Dict, List, Optional


def _str_or_none(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


# --- Products ---------------------------------------------------------------

# Fields whose change requires re-embedding the product (they feed the vector).
PRODUCT_TEXT_FIELDS = {"name", "description"}
# Fields stored in the Qdrant payload (a change here needs a payload sync).
PRODUCT_PAYLOAD_FIELDS = {
    "name",
    "description",
    "price",
    "currency",
    "availability",
    "categoryId",
    "branchId",
}


def product_payload(product: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a product."""
    return {
        "mongo_id": str(product.id),
        "name": product.name,
        "price": getattr(product, "price", None),
        "currency": getattr(product, "currency", None),
        "description": getattr(product, "description", "") or "",
        "branchId": _str_or_none(getattr(product, "branchId", None)),
        "categoryId": _str_or_none(getattr(product, "categoryId", None)),
        "availability": bool(getattr(product, "availability", False)),
    }


# --- Branches ---------------------------------------------------------------

BRANCH_TEXT_FIELDS = {"name", "tipos", "address"}
BRANCH_PAYLOAD_FIELDS = {
    "name",
    "tipos",
    "businessId",
    "isActive",
    "deliveryRadius",
    "coordinates",
}


def _branch_geo(branch: Any) -> Optional[Dict[str, float]]:
    """Return Qdrant geo payload {lon, lat} for a branch, or None if invalid."""
    coords_obj = getattr(branch, "coordinates", None)
    raw = getattr(coords_obj, "coordinates", None) if coords_obj is not None else None
    # Domain model stores [longitude, latitude]; some sources use plain lists.
    if isinstance(coords_obj, dict):
        raw = coords_obj.get("coordinates")
    if not raw or len(raw) < 2:
        return None
    try:
        lon, lat = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None
    # [0, 0] is almost always "unset" in this dataset — skip it.
    if lon == 0.0 and lat == 0.0:
        return None
    return {"lon": lon, "lat": lat}


def branch_payload(branch: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a branch."""
    payload: Dict[str, Any] = {
        "mongo_id": str(branch.id),
        "name": branch.name,
        "tipos": list(getattr(branch, "tipos", []) or []),
        "businessId": _str_or_none(getattr(branch, "businessId", None)),
        "isActive": bool(getattr(branch, "isActive", True)),
        "deliveryRadius": getattr(branch, "deliveryRadius", None),
    }
    geo = _branch_geo(branch)
    if geo is not None:
        payload["location"] = geo
    return payload


# --- Businesses -------------------------------------------------------------

BUSINESS_TEXT_FIELDS = {"name", "description"}
BUSINESS_PAYLOAD_FIELDS = {
    "name",
    "description",
    "globalRating",
    "approvalStatus",
    "isActive",
    "tags",
}


def business_payload(business: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a business."""
    return {
        "mongo_id": str(business.id),
        "name": business.name,
        "description": getattr(business, "description", "") or "",
        "globalRating": getattr(business, "globalRating", None),
        "approvalStatus": getattr(business, "approvalStatus", None),
        "isActive": bool(getattr(business, "isActive", True)),
        "tags": list(getattr(business, "tags", []) or []),
    }
