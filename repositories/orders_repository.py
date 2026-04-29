"""Repository classes for Orders, Delivery Persons, and Location Updates."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.orders import (
    BranchDeliveryRequest,
    DeliveryPerson,
    DeliveryRequestStatus,
    Order,
    OrderComment,
    OrderItem,
    OrderLocationUpdate,
    OrderStatus,
    OrderTimeline,
    PaymentStatus,
)


class OrderRepository:
    """Repository for order operations."""

    collection_name = "orders"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_order(doc: dict) -> Order:
        """Convert MongoDB document to Order model."""
        doc["_id"] = str(doc["_id"])
        return Order(**doc)

    async def create(self, order: Order) -> Order:
        """Create a new order."""
        collection = self._get_collection()
        doc = order.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["customerId"] = self._to_object_id(doc["customerId"])
        doc["branchId"] = self._to_object_id(doc["branchId"])
        doc["businessId"] = self._to_object_id(doc["businessId"])
        if doc.get("deliveryPersonId") is not None:
            doc["deliveryPersonId"] = self._to_object_id(doc["deliveryPersonId"])
        if doc.get("currentPaymentAttemptId") is not None:
            doc["currentPaymentAttemptId"] = self._to_object_id(
                doc["currentPaymentAttemptId"]
            )
        await collection.insert_one(doc)
        return order

    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"_id": self._to_object_id(order_id)})
        return self._doc_to_order(doc) if doc else None

    async def get_by_order_number(self, order_number: str) -> Optional[Order]:
        """Get order by order number."""
        collection = self._get_collection()
        doc = await collection.find_one({"orderNumber": order_number})
        return self._doc_to_order(doc) if doc else None

    async def get_by_customer(
        self,
        customer_id: str,
        status: Optional[OrderStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Order], int]:
        """Get orders by customer with pagination."""
        collection = self._get_collection()
        query: Dict[str, Any] = {"customerId": self._to_object_id(customer_id)}
        if status:
            query["status"] = status.value

        total = await collection.count_documents(query)
        cursor = collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
        orders = [self._doc_to_order(doc) async for doc in cursor]
        return orders, total

    async def get_by_branch(
        self,
        branch_id: str,
        status: Optional[OrderStatus] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Order], int]:
        """Get orders by branch with filters and pagination."""
        collection = self._get_collection()
        query: Dict[str, Any] = {"branchId": self._to_object_id(branch_id)}

        if status:
            query["status"] = status.value
        if from_date:
            query.setdefault("createdAt", {})["$gte"] = from_date
        if to_date:
            query.setdefault("createdAt", {})["$lte"] = to_date

        total = await collection.count_documents(query)
        cursor = collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
        orders = [self._doc_to_order(doc) async for doc in cursor]
        return orders, total

    async def get_active(
        self,
        branch_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Order], int]:
        """
        Get active orders (not cancelled and not delivered).

        If branch_id is provided, filters by a single branch; otherwise returns
        active orders across all branches.
        """
        collection = self._get_collection()
        query: Dict[str, Any] = {
            "status": {
                "$nin": [
                    OrderStatus.CANCELLED.value,
                    OrderStatus.DELIVERED.value,
                ]
            }
        }
        if branch_id:
            query["branchId"] = self._to_object_id(branch_id)

        total = await collection.count_documents(query)
        cursor = collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
        orders = [self._doc_to_order(doc) async for doc in cursor]
        return orders, total

    async def get_pending_by_branch(self, branch_id: str) -> List[Order]:
        """Get pending orders for a branch."""
        collection = self._get_collection()
        query = {
            "branchId": self._to_object_id(branch_id),
            "status": {
                "$in": [
                    OrderStatus.PENDING_ACCEPTANCE.value,
                    OrderStatus.AWAITING_DELIVERY_ACCEPTANCE.value,
                    OrderStatus.PENDING_PAYMENT.value,
                    OrderStatus.MODIFIED_BY_STORE.value,
                    OrderStatus.REJECTED_BY_STORE.value,
                ]
            },
        }
        cursor = collection.find(query).sort("createdAt", 1)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_ready_for_pickup_nearby(
        self, longitude: float, latitude: float, radius_km: float = 5.0
    ) -> List[Order]:
        """Get orders ready for pickup near a location using H3 index."""
        import h3

        from services.orders_utils import H3_RESOLUTION, coords_to_h3

        center_h3 = coords_to_h3(latitude, longitude, H3_RESOLUTION)
        # Cap radius to prevent excessive H3 cell generation
        capped_radius = min(radius_km, 100.0)
        # H3 resolution 7: average hex edge length ~1.22 km
        import math

        k = max(1, math.ceil(capped_radius / 1.22))
        nearby_cells = list(h3.grid_disk(center_h3, k))

        collection = self._get_collection()
        query = {
            "status": OrderStatus.READY_FOR_PICKUP.value,
            "deliveryPersonId": None,
            "branchH3": {"$in": nearby_cells},
        }
        cursor = collection.find(query).limit(50)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_ready_for_pickup_by_branches(
        self, branch_ids: List[str]
    ) -> List[Order]:
        """Get orders ready for pickup for specific linked branches."""
        collection = self._get_collection()
        query = {
            "status": OrderStatus.READY_FOR_PICKUP.value,
            "deliveryPersonId": None,
            "branchId": {"$in": [self._to_object_id(bid) for bid in branch_ids]},
        }
        cursor = collection.find(query).sort("createdAt", 1).limit(50)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_awaiting_delivery_acceptance_nearby(
        self, longitude: float, latitude: float, radius_km: float = 5.0
    ) -> List[Order]:
        """Get orders awaiting courier acceptance near a location using H3 index."""
        import h3

        from services.orders_utils import H3_RESOLUTION, coords_to_h3

        center_h3 = coords_to_h3(latitude, longitude, H3_RESOLUTION)
        capped_radius = min(radius_km, 100.0)
        import math

        k = max(1, math.ceil(capped_radius / 1.22))
        nearby_cells = list(h3.grid_disk(center_h3, k))

        collection = self._get_collection()
        query = {
            "status": OrderStatus.AWAITING_DELIVERY_ACCEPTANCE.value,
            "deliveryPersonId": None,
            "branchH3": {"$in": nearby_cells},
        }
        cursor = collection.find(query).sort("createdAt", 1).limit(50)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_awaiting_delivery_acceptance_by_branches(
        self, branch_ids: List[str]
    ) -> List[Order]:
        """Get orders awaiting courier acceptance for specific linked branches."""
        collection = self._get_collection()
        query = {
            "status": OrderStatus.AWAITING_DELIVERY_ACCEPTANCE.value,
            "deliveryPersonId": None,
            "branchId": {"$in": [self._to_object_id(bid) for bid in branch_ids]},
        }
        cursor = collection.find(query).sort("createdAt", 1).limit(50)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_current_delivery(self, delivery_person_id: str) -> Optional[Order]:
        """Get current order being delivered by a delivery person."""
        collection = self._get_collection()
        doc = await collection.find_one(
            {
                "deliveryPersonId": self._to_object_id(delivery_person_id),
                "status": {
                    "$in": [
                        OrderStatus.PENDING_PAYMENT.value,
                        OrderStatus.ACCEPTED.value,
                        OrderStatus.PREPARING.value,
                        OrderStatus.READY_FOR_PICKUP.value,
                        OrderStatus.ON_THE_WAY.value,
                    ]
                },
            }
        )
        return self._doc_to_order(doc) if doc else None

    async def update_status(
        self,
        order_id: str,
        status: OrderStatus,
        timeline_entry: OrderTimeline,
        extra_set_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Order]:
        """Update order status and add timeline entry."""
        collection = self._get_collection()
        now = datetime.utcnow()
        set_fields: Dict[str, Any] = {
            "status": status.value,
            "updatedAt": now,
            "lastStatusAt": now,
        }

        # Set delivery tracking timestamps based on status
        if status == OrderStatus.ON_THE_WAY:
            set_fields["pickedUpAt"] = now
        elif status == OrderStatus.DELIVERED:
            set_fields["completedAt"] = now
            # Calculate duration from assignment
            order = await self.get_by_id(order_id)
            if order and order.assignedAt:
                delta = now - order.assignedAt
                set_fields["deliveryDurationMin"] = int(delta.total_seconds() / 60)
        if extra_set_fields:
            set_fields.update(extra_set_fields)

        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": set_fields,
                "$push": {"timeline": timeline_entry.model_dump()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def mark_delivered_counted_for_customer(self, order_id: str) -> Optional[str]:
        """
        Mark an order as already counted for customer's deliveredOrdersCount.

        Returns customerId only on first successful mark. Subsequent calls return None.
        """
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {
                "_id": self._to_object_id(order_id),
                "status": OrderStatus.DELIVERED.value,
                "deliveryCountedForCustomer": {"$ne": True},
            },
            {
                "$set": {
                    "deliveryCountedForCustomer": True,
                    "updatedAt": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        if not result:
            return None
        customer_id = result.get("customerId")
        return str(customer_id) if customer_id is not None else None

    async def update_items(
        self,
        order_id: str,
        items: List[OrderItem],
        subtotal: float,
        service_charge: float,
        total: float,
        timeline_entry: OrderTimeline,
    ) -> Optional[Order]:
        """Update order items (for store modifications)."""
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": {
                    "items": [item.model_dump() for item in items],
                    "subtotal": subtotal,
                    "serviceCharge": service_charge,
                    "total": total,
                    "status": OrderStatus.MODIFIED_BY_STORE.value,
                    "deliveryPersonId": None,
                    "currentPaymentAttemptId": None,
                    "deadlineAt": now + timedelta(minutes=15),
                    "updatedAt": now,
                    "lastStatusAt": now,
                },
                "$push": {"timeline": timeline_entry.model_dump()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def resubmit_order(
        self,
        order_id: str,
        timeline_entry: OrderTimeline,
        items: Optional[List[OrderItem]] = None,
        subtotal: Optional[float] = None,
        service_charge: Optional[float] = None,
        total: Optional[float] = None,
    ) -> Optional[Order]:
        """Resubmit an order back to pending acceptance from pre-preparation states."""
        collection = self._get_collection()
        now = datetime.utcnow()
        set_fields: Dict[str, Any] = {
            "status": OrderStatus.PENDING_ACCEPTANCE.value,
            "deadlineAt": now + timedelta(minutes=15),
            "deliveryPersonId": None,
            "currentPaymentAttemptId": None,
            "paymentStatus": PaymentStatus.PENDING.value,
            "paymentId": None,
            "paidAt": None,
            "updatedAt": now,
            "lastStatusAt": now,
        }
        if items is not None:
            set_fields["items"] = [item.model_dump() for item in items]
        if subtotal is not None:
            set_fields["subtotal"] = subtotal
        if service_charge is not None:
            set_fields["serviceCharge"] = service_charge
        if total is not None:
            set_fields["total"] = total

        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": set_fields,
                "$inc": {"resubmissionCount": 1},
                "$push": {"timeline": timeline_entry.model_dump()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def get_expired_preparation_candidates(
        self,
        statuses: List[OrderStatus],
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Order]:
        """Get orders with elapsed deadlines before preparation."""
        collection = self._get_collection()
        current_time = now or datetime.utcnow()
        query = {
            "status": {"$in": [status.value for status in statuses]},
            "deadlineAt": {"$lte": current_time},
        }
        cursor = collection.find(query).sort("deadlineAt", 1).limit(limit)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def assign_delivery_person(
        self, order_id: str, delivery_person_id: str, estimated_delivery_time: datetime
    ) -> Optional[Order]:
        """Assign a delivery person to an order."""
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": {
                    "deliveryPersonId": self._to_object_id(delivery_person_id),
                    "estimatedDeliveryTime": estimated_delivery_time,
                    "assignedAt": now,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def set_delivery_person(
        self, order_id: str, delivery_person_id: str
    ) -> Optional[Order]:
        """Set reserved delivery person without delivery assignment timestamps."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {
                "_id": self._to_object_id(order_id),
                "status": OrderStatus.AWAITING_DELIVERY_ACCEPTANCE.value,
                "deliveryPersonId": None,
            },
            {
                "$set": {
                    "deliveryPersonId": self._to_object_id(delivery_person_id),
                    "updatedAt": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def clear_delivery_person(self, order_id: str) -> Optional[Order]:
        """Remove reserved delivery person from order."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": {
                    "deliveryPersonId": None,
                    "updatedAt": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def add_comment(
        self, order_id: str, comment: OrderComment
    ) -> Optional[Order]:
        """Add a comment to an order."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$push": {"comments": comment.model_dump()},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def add_rating(
        self, order_id: str, rating: int, comment: Optional[str] = None
    ) -> Optional[Order]:
        """Add rating to a delivered order."""
        collection = self._get_collection()
        update = {"$set": {"rating": rating, "updatedAt": datetime.utcnow()}}
        if comment:
            update["$set"]["ratingComment"] = comment

        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)}, update, return_document=True
        )
        return self._doc_to_order(result) if result else None

    async def update_delivery_fee(
        self,
        order_id: str,
        delivery_fee: float,
        total: float,
        delivery_mode: str = "branch",
    ) -> Optional[Order]:
        """Update delivery fee and total (for branch manual override)."""
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {
                "$set": {
                    "deliveryFee": delivery_fee,
                    "deliveryMode": delivery_mode,
                    "total": total,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def update_payment_status(
        self,
        order_id: str,
        payment_status: PaymentStatus,
        payment_id: Optional[str] = None,
    ) -> Optional[Order]:
        """Update payment status."""
        collection = self._get_collection()
        update: Dict[str, Any] = {
            "paymentStatus": payment_status.value,
            "updatedAt": datetime.utcnow(),
        }
        if payment_id:
            update["paymentId"] = payment_id

        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(order_id)},
            {"$set": update},
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def get_stats(
        self, branch_id: Optional[str], from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Get order statistics."""
        collection = self._get_collection()
        match_stage: Dict[str, Any] = {
            "createdAt": {"$gte": from_date, "$lte": to_date}
        }
        if branch_id:
            match_stage["branchId"] = self._to_object_id(branch_id)

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "totalOrders": {"$sum": 1},
                    "completedOrders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}
                    },
                    "cancelledOrders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}
                    },
                    "totalRevenue": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "delivered"]}, "$total", 0]
                        }
                    },
                }
            },
        ]

        result = await collection.aggregate(pipeline).to_list(1)
        if result:
            stats = result[0]
            stats.pop("_id", None)
            if stats["completedOrders"] > 0:
                stats["averageOrderValue"] = round(
                    stats["totalRevenue"] / stats["completedOrders"], 2
                )
            else:
                stats["averageOrderValue"] = 0
            stats["averageDeliveryTime"] = 30  # TODO: Calculate from timeline
            return stats

        return {
            "totalOrders": 0,
            "completedOrders": 0,
            "cancelledOrders": 0,
            "totalRevenue": 0,
            "averageOrderValue": 0,
            "averageDeliveryTime": 0,
        }

    async def get_dashboard_stats(
        self,
        business_id: str,
        from_date: datetime,
        to_date: datetime,
        branch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get dashboard statistics: revenue, completed, cancelled, top products."""
        collection = self._get_collection()
        match_stage: Dict[str, Any] = {
            "businessId": self._to_object_id(business_id),
            "createdAt": {"$gte": from_date, "$lte": to_date},
        }
        if branch_id:
            match_stage["branchId"] = self._to_object_id(branch_id)

        # Stats aggregation
        stats_pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "totalRevenue": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "delivered"]}, "$subtotal", 0]
                        }
                    },
                    "completedOrders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}
                    },
                    "cancelledOrders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}
                    },
                }
            },
        ]

        # Top products aggregation
        top_products_pipeline = [
            {"$match": {**match_stage, "status": "delivered"}},
            {"$unwind": "$items"},
            {
                "$match": {
                    "$or": [
                        {"items.itemType": "product"},
                        {"items.itemType": {"$exists": False}},  # Legacy orders
                    ]
                }
            },
            {
                "$group": {
                    "_id": {"$ifNull": ["$items.itemId", "$items.productId"]},
                    "name": {"$first": "$items.name"},
                    "imageUrl": {"$first": "$items.imageUrl"},
                    "totalQuantity": {"$sum": "$items.quantity"},
                    "totalRevenue": {
                        "$sum": {
                            "$multiply": [
                                {"$ifNull": ["$items.finalPrice", "$items.price"]},
                                "$items.quantity",
                            ]
                        }
                    },
                }
            },
            {"$sort": {"totalQuantity": -1}},
            {"$limit": 10},
        ]

        stats_result = await collection.aggregate(stats_pipeline).to_list(1)
        top_products = await collection.aggregate(top_products_pipeline).to_list(10)

        stats = stats_result[0] if stats_result else {}
        stats.pop("_id", None)

        return {
            "totalRevenue": round(stats.get("totalRevenue", 0), 2),
            "completedOrders": stats.get("completedOrders", 0),
            "cancelledOrders": stats.get("cancelledOrders", 0),
            "topProducts": [
                {
                    "productId": p["_id"],
                    "name": p["name"],
                    "imageUrl": p["imageUrl"],
                    "totalQuantity": p["totalQuantity"],
                    "totalRevenue": round(p["totalRevenue"], 2),
                }
                for p in top_products
            ],
        }

    async def get_by_delivery_person(
        self,
        delivery_person_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> List[Order]:
        """Get orders assigned to a delivery person, sorted by most recent."""
        collection = self._get_collection()
        query: Dict[str, Any] = {
            "deliveryPersonId": self._to_object_id(delivery_person_id)
        }
        if status:
            query["status"] = status
        skip = (page - 1) * page_size
        cursor = (
            collection.find(query).sort("completedAt", -1).skip(skip).limit(page_size)
        )
        return [self._doc_to_order(doc) async for doc in cursor]

    async def find_delivered_orders_for_delivery_person(
        self,
        delivery_person_id: str,
        query_filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        sort: Optional[List[Tuple[str, int]]] = None,
        projection: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query delivered orders for a delivery person using projection and stable sorting.

        This is intended for read-optimized courier history endpoints.
        """
        collection = self._get_collection()
        query: Dict[str, Any] = {
            "deliveryPersonId": self._to_object_id(delivery_person_id),
            "status": OrderStatus.DELIVERED.value,
            "completedAt": {"$ne": None},
        }
        if query_filters:
            query.update(query_filters)

        query_sort = sort or [("completedAt", -1), ("_id", -1)]
        cursor = (
            collection.find(query, projection=projection).sort(query_sort).limit(limit)
        )
        return [doc async for doc in cursor]

    async def count_delivered_orders_for_delivery_person(
        self,
        delivery_person_id: str,
        query_filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count delivered orders for a delivery person with optional extra filters."""
        collection = self._get_collection()
        query: Dict[str, Any] = {
            "deliveryPersonId": self._to_object_id(delivery_person_id),
            "status": OrderStatus.DELIVERED.value,
            "completedAt": {"$ne": None},
        }
        if query_filters:
            query.update(query_filters)
        return await collection.count_documents(query)

    async def get_delivery_person_stats(
        self, delivery_person_id: str
    ) -> Dict[str, Any]:
        """Get aggregated delivery stats for a delivery person."""
        collection = self._get_collection()
        pipeline = [
            {
                "$match": {
                    "deliveryPersonId": self._to_object_id(delivery_person_id),
                    "status": "delivered",
                }
            },
            {
                "$group": {
                    "_id": None,
                    "totalDeliveries": {"$sum": 1},
                    "totalEarnings": {"$sum": {"$ifNull": ["$deliveryEarnings", 0]}},
                    "totalDistanceKm": {
                        "$sum": {"$ifNull": ["$deliveryDistanceKm", 0]}
                    },
                    "avgDurationMin": {
                        "$avg": {"$ifNull": ["$deliveryDurationMin", 0]}
                    },
                    "avgRating": {"$avg": "$rating"},
                }
            },
        ]
        result = await collection.aggregate(pipeline).to_list(1)
        if result:
            stats = result[0]
            stats.pop("_id", None)
            stats["avgDurationMin"] = round(stats.get("avgDurationMin") or 0, 1)
            stats["avgRating"] = round(stats.get("avgRating") or 0, 2)
            stats["totalEarnings"] = round(stats.get("totalEarnings") or 0, 2)
            stats["totalDistanceKm"] = round(stats.get("totalDistanceKm") or 0, 2)
            return stats

        return {
            "totalDeliveries": 0,
            "totalEarnings": 0.0,
            "totalDistanceKm": 0.0,
            "avgDurationMin": 0,
            "avgRating": 0,
        }


class DeliveryPersonRepository:
    """Repository for delivery person operations."""

    collection_name = "delivery_persons"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_delivery_person(doc: dict) -> DeliveryPerson:
        """Convert MongoDB document to DeliveryPerson model."""
        doc["_id"] = str(doc["_id"])
        return DeliveryPerson(**doc)

    async def create(self, delivery_person: DeliveryPerson) -> DeliveryPerson:
        """Create a new delivery person."""
        collection = self._get_collection()
        doc = delivery_person.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["userId"] = self._to_object_id(doc["userId"])
        if doc.get("currentOrderId") is not None:
            doc["currentOrderId"] = self._to_object_id(doc["currentOrderId"])
        doc["linkedBranchIds"] = [
            self._to_object_id(bid) for bid in doc.get("linkedBranchIds", [])
        ]
        await collection.insert_one(doc)
        return delivery_person

    async def get_by_id(self, delivery_person_id: str) -> Optional[DeliveryPerson]:
        """Get delivery person by ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"_id": self._to_object_id(delivery_person_id)})
        return self._doc_to_delivery_person(doc) if doc else None

    async def get_by_user_id(self, user_id: str) -> Optional[DeliveryPerson]:
        """Get delivery person by user ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"userId": self._to_object_id(user_id)})
        return self._doc_to_delivery_person(doc) if doc else None

    async def get_available_nearby(
        self, longitude: float, latitude: float, radius_km: float = 5.0
    ) -> List[DeliveryPerson]:
        """Get available delivery persons near a location."""
        collection = self._get_collection()
        query = {
            "isActive": True,
            "isOnline": True,
            "currentOrderId": None,
            "currentLocation": {
                "$nearSphere": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                    "$maxDistance": radius_km * 1000,
                }
            },
        }
        cursor = collection.find(query).limit(20)
        return [self._doc_to_delivery_person(doc) async for doc in cursor]

    async def update_location(
        self, delivery_person_id: str, longitude: float, latitude: float
    ) -> Optional[DeliveryPerson]:
        """Update delivery person location."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {
                "$set": {
                    "currentLocation": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                    "updatedAt": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def update_online_status(
        self, delivery_person_id: str, is_online: bool
    ) -> Optional[DeliveryPerson]:
        """Update delivery person online status."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {"$set": {"isOnline": is_online, "updatedAt": datetime.utcnow()}},
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def assign_order(
        self, delivery_person_id: str, order_id: str
    ) -> Optional[DeliveryPerson]:
        """Assign an order to a delivery person."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {
                "$set": {
                    "currentOrderId": self._to_object_id(order_id),
                    "updatedAt": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def complete_delivery(
        self, delivery_person_id: str
    ) -> Optional[DeliveryPerson]:
        """Mark delivery as complete and increment counter."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {
                "$set": {"currentOrderId": None, "updatedAt": datetime.utcnow()},
                "$inc": {"totalDeliveries": 1},
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def add_linked_branch(
        self, delivery_person_id: str, branch_id: str
    ) -> Optional[DeliveryPerson]:
        """Add a branch to the delivery person's linked branches list."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {
                "$addToSet": {"linkedBranchIds": self._to_object_id(branch_id)},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def remove_linked_branch(
        self, delivery_person_id: str, branch_id: str
    ) -> Optional[DeliveryPerson]:
        """Remove a branch from the delivery person's linked branches list."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {
                "$pull": {"linkedBranchIds": self._to_object_id(branch_id)},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def unlink_all_from_branch(self, branch_id: str) -> int:
        """Remove a branch from all delivery persons' linkedBranchIds."""
        collection = self._get_collection()
        result = await collection.update_many(
            {"linkedBranchIds": self._to_object_id(branch_id)},
            {
                "$pull": {"linkedBranchIds": self._to_object_id(branch_id)},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )
        return result.modified_count

    async def update_rating(
        self, delivery_person_id: str, new_rating: float
    ) -> Optional[DeliveryPerson]:
        """Update delivery person rating (weighted average)."""
        collection = self._get_collection()
        dp = await self.get_by_id(delivery_person_id)
        if not dp:
            return None

        # Calculate weighted average
        total = dp.totalDeliveries
        if total == 0:
            avg_rating = new_rating
        else:
            avg_rating = ((dp.rating * total) + new_rating) / (total + 1)

        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(delivery_person_id)},
            {"$set": {"rating": round(avg_rating, 2), "updatedAt": datetime.utcnow()}},
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None


class OrderLocationRepository:
    """Repository for order location updates (tracking)."""

    collection_name = "order_location_updates"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_location_update(doc: dict) -> OrderLocationUpdate:
        """Convert MongoDB document to OrderLocationUpdate model."""
        doc["_id"] = str(doc["_id"])
        return OrderLocationUpdate(**doc)

    async def create(self, location_update: OrderLocationUpdate) -> OrderLocationUpdate:
        """Create a new location update."""
        collection = self._get_collection()
        doc = location_update.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["orderId"] = self._to_object_id(doc["orderId"])
        doc["deliveryPersonId"] = self._to_object_id(doc["deliveryPersonId"])
        await collection.insert_one(doc)
        return location_update

    async def get_latest_by_order(self, order_id: str) -> Optional[OrderLocationUpdate]:
        """Get the latest location update for an order."""
        collection = self._get_collection()
        doc = await collection.find_one(
            {"orderId": self._to_object_id(order_id)},
            sort=[("timestamp", -1)],
        )
        return self._doc_to_location_update(doc) if doc else None

    async def get_by_order(
        self, order_id: str, limit: int = 100
    ) -> List[OrderLocationUpdate]:
        """Get location updates for an order."""
        collection = self._get_collection()
        cursor = (
            collection.find({"orderId": self._to_object_id(order_id)})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return [self._doc_to_location_update(doc) async for doc in cursor]


class BranchDeliveryRequestRepository:
    """Repository for branch delivery request operations."""

    collection_name = "branch_delivery_requests"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_request(doc: dict) -> BranchDeliveryRequest:
        doc["_id"] = str(doc["_id"])
        return BranchDeliveryRequest(**doc)

    async def create(self, request: BranchDeliveryRequest) -> BranchDeliveryRequest:
        collection = self._get_collection()
        doc = request.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["deliveryPersonId"] = self._to_object_id(doc["deliveryPersonId"])
        doc["branchId"] = self._to_object_id(doc["branchId"])
        if doc.get("respondedBy") is not None:
            doc["respondedBy"] = self._to_object_id(doc["respondedBy"])
        await collection.insert_one(doc)
        return request

    async def get_by_id(self, request_id: str) -> Optional[BranchDeliveryRequest]:
        collection = self._get_collection()
        doc = await collection.find_one({"_id": self._to_object_id(request_id)})
        return self._doc_to_request(doc) if doc else None

    async def get_by_delivery_person(
        self,
        delivery_person_id: str,
        status: Optional[DeliveryRequestStatus] = None,
    ) -> List[BranchDeliveryRequest]:
        collection = self._get_collection()
        query: Dict[str, Any] = {
            "deliveryPersonId": self._to_object_id(delivery_person_id)
        }
        if status:
            query["status"] = status.value
        cursor = collection.find(query).sort("createdAt", -1)
        return [self._doc_to_request(doc) async for doc in cursor]

    async def get_by_branch(
        self,
        branch_id: str,
        status: Optional[DeliveryRequestStatus] = None,
    ) -> List[BranchDeliveryRequest]:
        collection = self._get_collection()
        query: Dict[str, Any] = {"branchId": self._to_object_id(branch_id)}
        if status:
            query["status"] = status.value
        cursor = collection.find(query).sort("createdAt", -1)
        return [self._doc_to_request(doc) async for doc in cursor]

    async def get_existing(
        self, delivery_person_id: str, branch_id: str
    ) -> Optional[BranchDeliveryRequest]:
        collection = self._get_collection()
        doc = await collection.find_one(
            {
                "deliveryPersonId": self._to_object_id(delivery_person_id),
                "branchId": self._to_object_id(branch_id),
            }
        )
        return self._doc_to_request(doc) if doc else None

    async def update_status(
        self,
        request_id: str,
        status: DeliveryRequestStatus,
        responded_by: str,
    ) -> Optional[BranchDeliveryRequest]:
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": self._to_object_id(request_id)},
            {
                "$set": {
                    "status": status.value,
                    "respondedBy": self._to_object_id(responded_by),
                    "respondedAt": now,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return self._doc_to_request(result) if result else None


async def create_order_indexes():
    """Create MongoDB indexes for orders collections."""
    db = get_database()

    # Orders indexes
    orders = db.orders
    await orders.create_index([("customerId", 1), ("createdAt", -1)])
    await orders.create_index([("branchId", 1), ("status", 1), ("createdAt", -1)])
    await orders.create_index("orderNumber", unique=True)
    await orders.create_index("status")
    await orders.create_index([("paymentStatus", 1), ("status", 1)])
    await orders.create_index([("status", 1), ("deadlineAt", 1)])
    # Compound index for delivery person pickup queries (H3-based geo)
    await orders.create_index([("status", 1), ("deliveryPersonId", 1), ("branchH3", 1)])
    await orders.create_index([("deliveryPersonId", 1), ("completedAt", -1)])
    await orders.create_index(
        [("deliveryPersonId", 1), ("completedAt", -1), ("_id", -1)],
        name="idx_delivery_person_completed_at_id",
    )
    await orders.create_index(
        [("deliveryPersonId", 1), ("completedAt", -1), ("_id", -1)],
        name="idx_delivery_person_completed_at_id_delivered_partial",
        partialFilterExpression={"status": OrderStatus.DELIVERED.value},
    )

    # Delivery persons indexes
    delivery_persons = db.delivery_persons
    await delivery_persons.create_index([("currentLocation", "2dsphere")])
    await delivery_persons.create_index([("isActive", 1), ("isOnline", 1)])
    await delivery_persons.create_index("userId", unique=True)

    # Order location updates indexes (with TTL)
    order_locations = db.order_location_updates
    await order_locations.create_index("orderId")
    await order_locations.create_index("timestamp", expireAfterSeconds=86400)

    print("✓ Order indexes created")


# Repository instances
orders_repo = OrderRepository()
delivery_persons_repo = DeliveryPersonRepository()
order_locations_repo = OrderLocationRepository()
branch_delivery_requests_repo = BranchDeliveryRequestRepository()
