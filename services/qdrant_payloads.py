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
# categoryId is included because the category name is part of the embedded text.
PRODUCT_TEXT_FIELDS = {"name", "description", "categoryId"}
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


def product_embedding_text(product: Any, category_name: Optional[str] = None) -> str:
    """Build the text embedded for a product.

    Including the category name gives the vector strong semantic context (two
    products with similar names but different categories no longer collide, and
    category-coherent recommendations get much stronger).
    """
    parts: List[str] = [product.name]
    if category_name:
        parts.append(f"Categoría: {category_name}")
    description = getattr(product, "description", "") or ""
    if description:
        parts.append(description)
    return ". ".join(parts).strip()


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


def branch_embedding_text(branch: Any) -> str:
    """Build the text embedded for a branch (name + tipos + address)."""
    parts: List[str] = [branch.name]
    tipos = ", ".join(getattr(branch, "tipos", []) or [])
    if tipos:
        parts.append(f"Tipos: {tipos}")
    address = getattr(branch, "address", "") or ""
    if address:
        parts.append(address)
    return ". ".join(parts).strip()


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

# tags is included because tags are part of the embedded text.
BUSINESS_TEXT_FIELDS = {"name", "description", "tags"}
BUSINESS_PAYLOAD_FIELDS = {
    "name",
    "description",
    "globalRating",
    "approvalStatus",
    "isActive",
    "tags",
}


def business_embedding_text(business: Any) -> str:
    """Build the text embedded for a business (name + description + tags)."""
    parts: List[str] = [business.name]
    description = getattr(business, "description", "") or ""
    if description:
        parts.append(description)
    tags = getattr(business, "tags", None) or []
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return ". ".join(parts).strip()


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
