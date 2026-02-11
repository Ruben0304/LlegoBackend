"""Repository classes for Orders, Delivery Persons, and Location Updates."""

from datetime import datetime
from typing import Any, Dict, List, Optional

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
    def _doc_to_order(doc: dict) -> Order:
        """Convert MongoDB document to Order model."""
        doc["_id"] = str(doc["_id"])
        return Order(**doc)

    async def create(self, order: Order) -> Order:
        """Create a new order."""
        collection = self._get_collection()
        doc = order.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return order

    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"_id": ObjectId(order_id)})
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
        query: Dict[str, Any] = {"customerId": customer_id}
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
        query: Dict[str, Any] = {"branchId": branch_id}

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

    async def get_pending_by_branch(self, branch_id: str) -> List[Order]:
        """Get pending orders for a branch."""
        collection = self._get_collection()
        query = {
            "branchId": branch_id,
            "status": {
                "$in": [
                    OrderStatus.PENDING_ACCEPTANCE.value,
                    OrderStatus.MODIFIED_BY_STORE.value,
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
            "branchId": {"$in": branch_ids},
        }
        cursor = collection.find(query).sort("createdAt", 1).limit(50)
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_current_delivery(self, delivery_person_id: str) -> Optional[Order]:
        """Get current order being delivered by a delivery person."""
        collection = self._get_collection()
        doc = await collection.find_one(
            {
                "deliveryPersonId": delivery_person_id,
                "status": {
                    "$in": [
                        OrderStatus.READY_FOR_PICKUP.value,
                        OrderStatus.ON_THE_WAY.value,
                    ]
                },
            }
        )
        return self._doc_to_order(doc) if doc else None

    async def update_status(
        self, order_id: str, status: OrderStatus, timeline_entry: OrderTimeline
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

        result = await collection.find_one_and_update(
            {"_id": ObjectId(order_id)},
            {
                "$set": set_fields,
                "$push": {"timeline": timeline_entry.model_dump()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def update_items(
        self,
        order_id: str,
        items: List[OrderItem],
        subtotal: float,
        total: float,
        timeline_entry: OrderTimeline,
    ) -> Optional[Order]:
        """Update order items (for store modifications)."""
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": ObjectId(order_id)},
            {
                "$set": {
                    "items": [item.model_dump() for item in items],
                    "subtotal": subtotal,
                    "total": total,
                    "status": OrderStatus.MODIFIED_BY_STORE.value,
                    "updatedAt": now,
                    "lastStatusAt": now,
                },
                "$push": {"timeline": timeline_entry.model_dump()},
            },
            return_document=True,
        )
        return self._doc_to_order(result) if result else None

    async def assign_delivery_person(
        self, order_id: str, delivery_person_id: str, estimated_delivery_time: datetime
    ) -> Optional[Order]:
        """Assign a delivery person to an order."""
        collection = self._get_collection()
        now = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": ObjectId(order_id)},
            {
                "$set": {
                    "deliveryPersonId": delivery_person_id,
                    "estimatedDeliveryTime": estimated_delivery_time,
                    "assignedAt": now,
                    "updatedAt": now,
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
            {"_id": ObjectId(order_id)},
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
            {"_id": ObjectId(order_id)}, update, return_document=True
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
            {"_id": ObjectId(order_id)},
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
            {"_id": ObjectId(order_id)}, {"$set": update}, return_document=True
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
            match_stage["branchId"] = branch_id

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
        self, business_id: str, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Get dashboard statistics: revenue, completed, cancelled, top products."""
        collection = self._get_collection()
        match_stage: Dict[str, Any] = {
            "businessId": business_id,
            "createdAt": {"$gte": from_date, "$lte": to_date},
        }

        # Stats aggregation
        stats_pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "totalRevenue": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "delivered"]}, "$total", 0]
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
                "$group": {
                    "_id": "$items.productId",
                    "name": {"$first": "$items.name"},
                    "imageUrl": {"$first": "$items.imageUrl"},
                    "totalQuantity": {"$sum": "$items.quantity"},
                    "totalRevenue": {
                        "$sum": {"$multiply": ["$items.price", "$items.quantity"]}
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
        query: Dict[str, Any] = {"deliveryPersonId": delivery_person_id}
        if status:
            query["status"] = status
        skip = (page - 1) * page_size
        cursor = (
            collection.find(query).sort("completedAt", -1).skip(skip).limit(page_size)
        )
        return [self._doc_to_order(doc) async for doc in cursor]

    async def get_delivery_person_stats(
        self, delivery_person_id: str
    ) -> Dict[str, Any]:
        """Get aggregated delivery stats for a delivery person."""
        collection = self._get_collection()
        pipeline = [
            {"$match": {"deliveryPersonId": delivery_person_id, "status": "delivered"}},
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
    def _doc_to_delivery_person(doc: dict) -> DeliveryPerson:
        """Convert MongoDB document to DeliveryPerson model."""
        doc["_id"] = str(doc["_id"])
        return DeliveryPerson(**doc)

    async def create(self, delivery_person: DeliveryPerson) -> DeliveryPerson:
        """Create a new delivery person."""
        collection = self._get_collection()
        doc = delivery_person.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return delivery_person

    async def get_by_id(self, delivery_person_id: str) -> Optional[DeliveryPerson]:
        """Get delivery person by ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"_id": ObjectId(delivery_person_id)})
        return self._doc_to_delivery_person(doc) if doc else None

    async def get_by_user_id(self, user_id: str) -> Optional[DeliveryPerson]:
        """Get delivery person by user ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"userId": user_id})
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
            {"_id": ObjectId(delivery_person_id)},
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
            {"_id": ObjectId(delivery_person_id)},
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
            {"_id": ObjectId(delivery_person_id)},
            {"$set": {"currentOrderId": order_id, "updatedAt": datetime.utcnow()}},
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

    async def complete_delivery(
        self, delivery_person_id: str
    ) -> Optional[DeliveryPerson]:
        """Mark delivery as complete and increment counter."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": ObjectId(delivery_person_id)},
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
            {"_id": ObjectId(delivery_person_id)},
            {
                "$addToSet": {"linkedBranchIds": branch_id},
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
            {"_id": ObjectId(delivery_person_id)},
            {
                "$pull": {"linkedBranchIds": branch_id},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return self._doc_to_delivery_person(result) if result else None

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
            {"_id": ObjectId(delivery_person_id)},
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
    def _doc_to_location_update(doc: dict) -> OrderLocationUpdate:
        """Convert MongoDB document to OrderLocationUpdate model."""
        doc["_id"] = str(doc["_id"])
        return OrderLocationUpdate(**doc)

    async def create(self, location_update: OrderLocationUpdate) -> OrderLocationUpdate:
        """Create a new location update."""
        collection = self._get_collection()
        doc = location_update.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return location_update

    async def get_latest_by_order(self, order_id: str) -> Optional[OrderLocationUpdate]:
        """Get the latest location update for an order."""
        collection = self._get_collection()
        doc = await collection.find_one({"orderId": order_id}, sort=[("timestamp", -1)])
        return self._doc_to_location_update(doc) if doc else None

    async def get_by_order(
        self, order_id: str, limit: int = 100
    ) -> List[OrderLocationUpdate]:
        """Get location updates for an order."""
        collection = self._get_collection()
        cursor = (
            collection.find({"orderId": order_id}).sort("timestamp", -1).limit(limit)
        )
        return [self._doc_to_location_update(doc) async for doc in cursor]


class BranchDeliveryRequestRepository:
    """Repository for branch delivery request operations."""

    collection_name = "branch_delivery_requests"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _doc_to_request(doc: dict) -> BranchDeliveryRequest:
        doc["_id"] = str(doc["_id"])
        return BranchDeliveryRequest(**doc)

    async def create(self, request: BranchDeliveryRequest) -> BranchDeliveryRequest:
        collection = self._get_collection()
        doc = request.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return request

    async def get_by_id(self, request_id: str) -> Optional[BranchDeliveryRequest]:
        collection = self._get_collection()
        doc = await collection.find_one({"_id": ObjectId(request_id)})
        return self._doc_to_request(doc) if doc else None

    async def get_by_delivery_person(
        self,
        delivery_person_id: str,
        status: Optional[DeliveryRequestStatus] = None,
    ) -> List[BranchDeliveryRequest]:
        collection = self._get_collection()
        query: Dict[str, Any] = {"deliveryPersonId": delivery_person_id}
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
        query: Dict[str, Any] = {"branchId": branch_id}
        if status:
            query["status"] = status.value
        cursor = collection.find(query).sort("createdAt", -1)
        return [self._doc_to_request(doc) async for doc in cursor]

    async def get_existing(
        self, delivery_person_id: str, branch_id: str
    ) -> Optional[BranchDeliveryRequest]:
        collection = self._get_collection()
        doc = await collection.find_one(
            {"deliveryPersonId": delivery_person_id, "branchId": branch_id}
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
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": status.value,
                    "respondedBy": responded_by,
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
    # Compound index for delivery person pickup queries (H3-based geo)
    await orders.create_index([("status", 1), ("deliveryPersonId", 1), ("branchH3", 1)])
    await orders.create_index([("deliveryPersonId", 1), ("completedAt", -1)])

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
