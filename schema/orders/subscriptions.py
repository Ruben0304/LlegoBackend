"""GraphQL subscriptions for real-time order updates."""
import strawberry
from typing import AsyncGenerator
import asyncio

from .types import OrderType, DeliveryLocationUpdateType, CoordinatesType, order_to_type
from repositories.orders_repository import orders_repo


# In-memory pub/sub for demo (replace with Redis in production)
class OrderPubSub:
    """Simple in-memory pub/sub for order updates."""
    
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
    
    async def subscribe(self, channel: str) -> asyncio.Queue:
        """Subscribe to a channel."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[channel].append(queue)
        return queue
    
    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        """Unsubscribe from a channel."""
        if channel in self._subscribers:
            self._subscribers[channel].remove(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]
    
    async def publish(self, channel: str, message):
        """Publish a message to a channel."""
        if channel in self._subscribers:
            for queue in self._subscribers[channel]:
                await queue.put(message)


# Global pub/sub instance
order_pubsub = OrderPubSub()


async def publish_order_update(order_id: str, order):
    """Publish order update to subscribers."""
    await order_pubsub.publish(f"order:{order_id}", order)


async def publish_branch_order(branch_id: str, order):
    """Publish new/updated order to branch subscribers."""
    await order_pubsub.publish(f"branch:{branch_id}", order)


async def publish_delivery_location(order_id: str, location_update: dict):
    """Publish delivery location update."""
    await order_pubsub.publish(f"delivery_location:{order_id}", location_update)


@strawberry.type
class OrderSubscription:
    @strawberry.subscription(description="Escuchar cambios en un pedido específico")
    async def order_updated(self, orderId: str) -> AsyncGenerator[OrderType, None]:
        """Subscribe to order updates."""
        queue = await order_pubsub.subscribe(f"order:{orderId}")
        try:
            while True:
                order = await queue.get()
                yield order_to_type(order)
        finally:
            await order_pubsub.unsubscribe(f"order:{orderId}", queue)
    
    @strawberry.subscription(description="Ubicación del repartidor en tiempo real")
    async def delivery_location_updated(
        self,
        orderId: str
    ) -> AsyncGenerator[DeliveryLocationUpdateType, None]:
        """Subscribe to delivery location updates."""
        queue = await order_pubsub.subscribe(f"delivery_location:{orderId}")
        try:
            while True:
                update = await queue.get()
                yield DeliveryLocationUpdateType(
                    orderId=update["orderId"],
                    location=CoordinatesType(
                        type="Point",
                        coordinates=[update["longitude"], update["latitude"]]
                    ),
                    timestamp=update["timestamp"],
                    estimatedMinutesRemaining=update.get("estimatedMinutes"),
                    distanceRemainingKm=update.get("distanceKm")
                )
        finally:
            await order_pubsub.unsubscribe(f"delivery_location:{orderId}", queue)
    
    @strawberry.subscription(description="Nuevos pedidos para una sucursal")
    async def new_branch_order(self, branchId: str) -> AsyncGenerator[OrderType, None]:
        """Subscribe to new orders for a branch."""
        queue = await order_pubsub.subscribe(f"branch:{branchId}")
        try:
            while True:
                order = await queue.get()
                yield order_to_type(order)
        finally:
            await order_pubsub.unsubscribe(f"branch:{branchId}", queue)
    
    @strawberry.subscription(description="Cambios en pedidos de una sucursal")
    async def branch_order_updated(self, branchId: str) -> AsyncGenerator[OrderType, None]:
        """Subscribe to order updates for a branch."""
        queue = await order_pubsub.subscribe(f"branch_updates:{branchId}")
        try:
            while True:
                order = await queue.get()
                yield order_to_type(order)
        finally:
            await order_pubsub.unsubscribe(f"branch_updates:{branchId}", queue)
