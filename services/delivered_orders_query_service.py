"""Read-optimized query service for courier delivered orders history."""

from __future__ import annotations

import base64
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from clients.mongodb_client import get_database
from repositories.orders_repository import orders_repo

logger = logging.getLogger(__name__)

MAX_FIRST = 50
DEFAULT_FIRST = 20
MAX_SEARCH_LENGTH = 64


class DeliveredOrdersQueryService:
    """Encapsulates filtering, cursor pagination, and projection for delivered orders."""

    @staticmethod
    def encode_cursor(delivered_at: datetime, order_id: str) -> str:
        """Encode keyset cursor as base64(timestamp_ms|order_id)."""
        if delivered_at.tzinfo is None:
            delivered_at = delivered_at.replace(tzinfo=timezone.utc)
        timestamp_ms = int(delivered_at.timestamp() * 1000)
        raw = f"{timestamp_ms}|{order_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_cursor(cursor: str) -> Tuple[datetime, str]:
        """Decode keyset cursor and validate format."""
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
            timestamp_ms_raw, order_id = decoded.split("|", 1)
            timestamp_ms = int(timestamp_ms_raw)
            if not order_id:
                raise ValueError("cursor order_id is empty")
            delivered_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            return delivered_at, order_id
        except Exception as exc:
            raise ValueError("Cursor inválido") from exc

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _normalize_first(first: Optional[int]) -> int:
        if first is None:
            return DEFAULT_FIRST
        if first <= 0:
            raise ValueError("first debe ser mayor que 0")
        return min(first, MAX_FIRST)

    def _build_query_filters(
        self,
        *,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        search: Optional[str],
        branch_id: Optional[str],
        city: Optional[str],
        after: Optional[str],
    ) -> Dict[str, Any]:
        query_filters: Dict[str, Any] = {}

        if from_date and to_date and from_date > to_date:
            raise ValueError("from no puede ser mayor que to")

        completed_at_filter: Dict[str, Any] = {}
        if from_date:
            completed_at_filter["$gte"] = from_date
        if to_date:
            completed_at_filter["$lte"] = to_date

        if after:
            cursor_completed_at, cursor_order_id = self.decode_cursor(after)
            cursor_id = self._to_object_id(cursor_order_id)
            query_filters["$or"] = [
                {"completedAt": {"$lt": cursor_completed_at}},
                {
                    "$and": [
                        {"completedAt": cursor_completed_at},
                        {"_id": {"$lt": cursor_id}},
                    ]
                },
            ]

        if completed_at_filter:
            query_filters["completedAt"] = completed_at_filter

        if branch_id:
            query_filters["branchId"] = self._to_object_id(branch_id)

        if city:
            query_filters["deliveryAddress.city"] = {
                "$regex": f"^{re.escape(city.strip())}$",
                "$options": "i",
            }

        if search:
            normalized_search = search.strip()
            if len(normalized_search) > MAX_SEARCH_LENGTH:
                raise ValueError("search excede el tamaño máximo permitido")
            search_filters: List[Dict[str, Any]] = [
                {
                    "orderNumber": {
                        "$regex": re.escape(normalized_search),
                        "$options": "i",
                    }
                }
            ]
            if ObjectId.is_valid(normalized_search):
                search_filters.append({"_id": ObjectId(normalized_search)})
            query_filters["$and"] = query_filters.get("$and", []) + [
                {"$or": search_filters}
            ]

        return query_filters

    @staticmethod
    def _derive_final_status(doc: Dict[str, Any]) -> str:
        if doc.get("fraudHidden") is True:
            return "fraud_hidden"
        fraud_review = doc.get("fraudReview") or {}
        if (
            isinstance(fraud_review, dict)
            and fraud_review.get("hiddenForCourier") is True
        ):
            return "fraud_hidden"

        if doc.get("isReversed") is True:
            return "reversed"
        reversal_status = str(doc.get("reversalStatus") or "").lower()
        if reversal_status in {"reversed", "chargeback", "charged_back"}:
            return "reversed"

        if doc.get("isDisputed") is True:
            return "disputed"
        dispute_status = str(doc.get("disputeStatus") or "").lower()
        if dispute_status in {"open", "under_review", "resolved", "won", "lost"}:
            return "disputed"

        return "delivered"

    @staticmethod
    def _has_delivery_evidence(doc: Dict[str, Any]) -> bool:
        if doc.get("deliveryCodeVerifiedAt"):
            return True
        evidence_refs = doc.get("deliveryEvidenceRefs")
        if isinstance(evidence_refs, list) and len(evidence_refs) > 0:
            return True
        if doc.get("deliveryProofUrl"):
            return True
        return False

    @staticmethod
    def _resolve_visible_amount(doc: Dict[str, Any]) -> float:
        for key in ("deliveryEarnings", "deliveryFee", "total"):
            value = doc.get(key)
            if isinstance(value, (int, float)):
                return round(float(value), 2)
        return 0.0

    async def _resolve_branch_names(self, docs: List[Dict[str, Any]]) -> Dict[str, str]:
        branch_ids = []
        for doc in docs:
            branch_id = doc.get("branchId")
            if branch_id is not None:
                branch_ids.append(branch_id)

        unique_ids = list({bid for bid in branch_ids})
        if not unique_ids:
            return {}

        db = get_database()
        cursor = db.branches.find(
            {"_id": {"$in": unique_ids}},
            projection={"name": 1},
        )
        result = await cursor.to_list(length=None)
        return {str(item["_id"]): item.get("name") or "" for item in result}

    async def _resolve_customer_names(
        self, docs: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        customer_ids = []
        for doc in docs:
            customer_id = doc.get("customerId")
            if customer_id is not None:
                customer_ids.append(customer_id)

        unique_ids = list({cid for cid in customer_ids})
        if not unique_ids:
            return {}

        db = get_database()
        cursor = db.users.find(
            {"_id": {"$in": unique_ids}},
            projection={"name": 1},
        )
        result = await cursor.to_list(length=None)
        names: Dict[str, str] = {}
        for item in result:
            raw_name = (item.get("name") or "").strip()
            names[str(item["_id"])] = raw_name if raw_name else "Cliente"
        return names

    async def list_for_courier(
        self,
        *,
        courier_id: str,
        first: Optional[int],
        after: Optional[str],
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        search: Optional[str],
        branch_id: Optional[str],
        city: Optional[str],
        include_fraud_hidden: bool = False,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        page_size = self._normalize_first(first)

        query_filters = self._build_query_filters(
            from_date=from_date,
            to_date=to_date,
            search=search,
            branch_id=branch_id,
            city=city,
            after=after,
        )

        projection = {
            "_id": 1,
            "orderNumber": 1,
            "completedAt": 1,
            "branchId": 1,
            "customerId": 1,
            "deliveryAddress.street": 1,
            "deliveryAddress.city": 1,
            "deliveryEarnings": 1,
            "deliveryFee": 1,
            "total": 1,
            "currency": 1,
            "deliveryCodeVerifiedAt": 1,
            "deliveryEvidenceRefs": 1,
            "deliveryProofUrl": 1,
            "isDisputed": 1,
            "disputeStatus": 1,
            "isReversed": 1,
            "reversalStatus": 1,
            "fraudHidden": 1,
            "fraudReview.hiddenForCourier": 1,
        }

        docs = await orders_repo.find_delivered_orders_for_delivery_person(
            delivery_person_id=courier_id,
            query_filters=query_filters,
            limit=page_size + 1,
            sort=[("completedAt", -1), ("_id", -1)],
            projection=projection,
        )

        has_next = len(docs) > page_size
        docs_page = docs[:page_size]

        branch_names = await self._resolve_branch_names(docs_page)
        customer_names = await self._resolve_customer_names(docs_page)

        edges: List[Dict[str, Any]] = []
        for doc in docs_page:
            final_status = self._derive_final_status(doc)
            if final_status == "fraud_hidden" and not include_fraud_hidden:
                continue

            completed_at = doc.get("completedAt")
            if not isinstance(completed_at, datetime):
                continue

            order_id = str(doc.get("_id"))
            cursor = self.encode_cursor(completed_at, order_id)

            delivery_address = doc.get("deliveryAddress") or {}
            customer_name = customer_names.get(str(doc.get("customerId"))) or "Cliente"

            edges.append(
                {
                    "cursor": cursor,
                    "node": {
                        "orderId": order_id,
                        "orderNumber": doc.get("orderNumber") or "",
                        "deliveredAt": completed_at,
                        "merchantName": branch_names.get(str(doc.get("branchId")))
                        or "",
                        "customerDisplayName": customer_name,
                        "addressSummary": delivery_address.get("street") or "",
                        "city": delivery_address.get("city"),
                        "visibleAmount": self._resolve_visible_amount(doc),
                        "currency": doc.get("currency") or "USD",
                        "finalStatus": final_status,
                        "hasDeliveryEvidence": self._has_delivery_evidence(doc),
                    },
                }
            )

        end_cursor = edges[-1]["cursor"] if edges else None

        total_count = await orders_repo.count_delivered_orders_for_delivery_person(
            delivery_person_id=courier_id,
            query_filters={k: v for k, v in query_filters.items() if k not in {"$or"}},
        )

        query_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "delivered_orders_query courier_id=%s page_size=%s has_next=%s result_count=%s query_ms=%s",
            courier_id,
            page_size,
            has_next,
            len(edges),
            query_ms,
        )

        return {
            "edges": edges,
            "pageInfo": {
                "hasNextPage": has_next,
                "endCursor": end_cursor,
            },
            "totalCount": total_count,
        }


delivered_orders_query_service = DeliveredOrdersQueryService()
