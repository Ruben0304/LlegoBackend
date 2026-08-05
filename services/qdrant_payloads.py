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


def _get(entity: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a domain object or a raw Mongo dict.

    Lets the builders run over raw documents (e.g. products missing optional
    fields like weight/image that would fail strict model validation) during
    backfills, while still working with domain objects on the write path.
    """
    if isinstance(entity, dict):
        return entity.get(key, default)
    return getattr(entity, key, default)


def _entity_id(entity: Any) -> str:
    """Get the mongo id whether the entity is a domain object or a raw dict."""
    if isinstance(entity, dict):
        return str(entity.get("_id") or entity.get("id"))
    return str(entity.id)


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
    parts: List[str] = [_get(product, "name", "")]
    if category_name:
        parts.append(f"Categoría: {category_name}")
    description = _get(product, "description", "") or ""
    if description:
        parts.append(description)
    return ". ".join(parts).strip()


def product_payload(product: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a product (object or raw dict)."""
    return {
        "mongo_id": _entity_id(product),
        "name": _get(product, "name", ""),
        "price": _get(product, "price"),
        "currency": _get(product, "currency"),
        "description": _get(product, "description", "") or "",
        "branchId": _str_or_none(_get(product, "branchId")),
        "categoryId": _str_or_none(_get(product, "categoryId")),
        "availability": bool(_get(product, "availability", False)),
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
    coords_obj = _get(branch, "coordinates")
    # Domain model stores [longitude, latitude]; raw Mongo docs nest it in a dict.
    if isinstance(coords_obj, dict):
        raw = coords_obj.get("coordinates")
    else:
        raw = getattr(coords_obj, "coordinates", None) if coords_obj is not None else None
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
    parts: List[str] = [_get(branch, "name", "")]
    tipos = ", ".join(_get(branch, "tipos", []) or [])
    if tipos:
        parts.append(f"Tipos: {tipos}")
    address = _get(branch, "address", "") or ""
    if address:
        parts.append(address)
    return ". ".join(parts).strip()


def branch_payload(branch: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a branch (object or raw dict)."""
    payload: Dict[str, Any] = {
        "mongo_id": _entity_id(branch),
        "name": _get(branch, "name", ""),
        "tipos": list(_get(branch, "tipos", []) or []),
        "businessId": _str_or_none(_get(branch, "businessId")),
        "isActive": bool(_get(branch, "isActive", True)),
        "deliveryRadius": _get(branch, "deliveryRadius"),
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
    parts: List[str] = [_get(business, "name", "")]
    description = _get(business, "description", "") or ""
    if description:
        parts.append(description)
    tags = _get(business, "tags", None) or []
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return ". ".join(parts).strip()


def business_payload(business: Any) -> Dict[str, Any]:
    """Build the enriched Qdrant payload for a business (object or raw dict)."""
    return {
        "mongo_id": _entity_id(business),
        "name": _get(business, "name", ""),
        "description": _get(business, "description", "") or "",
        "globalRating": _get(business, "globalRating"),
        "approvalStatus": _get(business, "approvalStatus"),
        "isActive": bool(_get(business, "isActive", True)),
        "tags": list(_get(business, "tags", []) or []),
    }
