"""GraphQL subscriptions for real-time order updates."""
import json
import strawberry
from datetime import datetime
from typing import AsyncGenerator, Optional, List
import asyncio

from strawberry.types import Info
from utils.graphql_auth import require_auth
from utils.rate_limit import redis_client

from .types import (
    OrderType,
    DeliveryLocationUpdateType,
    CoordinatesType,
    OrderTrackingStreamPayload,
    CourierPresenceType,
    order_to_type,
)
from repositories.orders_repository import orders_repo

COURIER_ONLINE_KEY_PREFIX = "presence:courier:"


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Supports the isoformat() we stored (naive UTC)
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _redis_fetch_courier_presence_snapshot_sync() -> List[CourierPresenceType]:
    """
    Sync Redis read: returns a snapshot of currently-online couriers.

    Uses scan_iter (safe-ish) and a pipeline for efficiency.
    This runs in a worker thread from the async subscription.
    """
    if redis_client is None:
        return []

    loc_keys = list(
        redis_client.scan_iter(match=f"{COURIER_ONLINE_KEY_PREFIX}*:loc", count=200)
    )
    if not loc_keys:
        return []

    pipe = redis_client.pipeline()
    for k in loc_keys:
        pipe.get(k)
    loc_values = pipe.execute()

    results: List[CourierPresenceType] = []
    for key, raw in zip(loc_keys, loc_values):
        if not raw:
            continue
        # key: presence:courier:{id}:loc
        try:
            parts = str(key).split(":")
            delivery_person_id = parts[2]  # courier:{id}
            if delivery_person_id == "courier":
                # Unexpected shape; skip
                continue
        except Exception:
            continue

        try:
            payload = json.loads(raw)
        except Exception:
            continue

        coords = payload.get("coordinates") or []
        location = None
        if isinstance(coords, list) and len(coords) >= 2:
            try:
                location = CoordinatesType(
                    type=payload.get("type") or "Point",
                    coordinates=[float(coords[0]), float(coords[1])],
                )
            except Exception:
                location = None

        results.append(
            CourierPresenceType(
                deliveryPersonId=str(delivery_person_id),
                isOnline=True,
                location=location,
                timestamp=_parse_iso_dt(payload.get("timestamp")),
                orderId=payload.get("orderId"),
            )
        )
    return results


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


async def publish_order_tracking(order_id: str, tracking_data: OrderTrackingStreamPayload):
    """Publish order tracking update for streaming subscription."""
    await order_pubsub.publish(f"order_tracking:{order_id}", tracking_data)


@strawberry.type
class OrderSubscription:
    @strawberry.subscription(
        description="Mensajeros online y su ubicación (snapshot periódico desde Redis)"
    )
    async def couriers_presence_stream(
        self,
        info: Info,
        jwt: Optional[str] = None,
        intervalSeconds: float = 2.0,
    ) -> AsyncGenerator[List[CourierPresenceType], None]:
        """
        WebSocket subscription that periodically emits a snapshot of online couriers.

        - Fuente: Redis keys `presence:courier:{id}:loc` (con TTL)
        - Para 50 mensajeros, polling cada ~2s es suficiente y simple.
        """
        # Auth (allow jwt param or connection_init context)
        user_id = None
        if isinstance(info.context, dict):
            user_id = info.context.get("user_id")
        else:
            user_id = getattr(info.context, "user_id", None)
        if not user_id and jwt:
            user_id = require_auth(jwt, info)
        if not user_id:
            raise Exception("Autenticación requerida. Proporciona un JWT válido.")

        # Guard interval
        effective_interval = max(0.5, float(intervalSeconds or 2.0))

        while True:
            snapshot = await asyncio.to_thread(_redis_fetch_courier_presence_snapshot_sync)
            yield snapshot
            await asyncio.sleep(effective_interval)

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

    @strawberry.subscription(description="Stream de seguimiento de pedido en tiempo real")
    async def order_tracking_stream(
        self,
        info: Info,
        orderId: str,
        jwt: Optional[str] = None,
    ) -> AsyncGenerator[OrderTrackingStreamPayload, None]:
        """
        Subscribe to real-time order tracking updates.

        Compatible with graphql-transport-ws protocol.
        Emits events when order status, delivery location, or ETA changes.

        Args:
            orderId: ID of the order to track
            jwt: Authentication token (can also be provided in connection_init)

        Yields:
            OrderTrackingStreamPayload with current tracking information
        """
        print(f"\n{'=' * 80}")
        print(f"[ORDER TRACKING STREAM] Starting tracking session for order: {orderId}")

        try:
            # Authentication - support both connection_init and subscription variables
            user_id = None
            try:
                # Try to get user_id from context (set by connection_init)
                if isinstance(info.context, dict):
                    user_id = info.context.get("user_id")
                else:
                    user_id = getattr(info.context, "user_id", None)

                # If not in context, try jwt parameter
                if not user_id and jwt:
                    user_id = require_auth(jwt, info)

                if not user_id:
                    raise Exception("Autenticación requerida. Proporciona un JWT válido.")

            except Exception as e:
                print(f"[ORDER TRACKING STREAM] Authentication failed: {e}")
                print(f"{'=' * 80}\n")
                raise Exception("Autenticación requerida. Proporciona un JWT válido en connection_init o como parámetro jwt.")

            print(f"[ORDER TRACKING STREAM] User authenticated: {user_id}")

            # Verify order access
            order = await orders_repo.get_by_id(orderId)
            if not order:
                print(f"[ORDER TRACKING STREAM] Order not found: {orderId}")
                print(f"{'=' * 80}\n")
                raise Exception("Pedido no encontrado")

            # TODO: Add authorization check similar to get_order_tracking
            # For now, just verify it exists

            print(f"[ORDER TRACKING STREAM] Order found, subscribing to updates...")

            # Subscribe to tracking channel
            queue = await order_pubsub.subscribe(f"order_tracking:{orderId}")

            # Send initial state immediately
            from services.orders_service import order_service
            try:
                initial_tracking = await order_service.get_order_tracking(orderId, user_id)

                # Build initial payload
                dp_loc = initial_tracking.get("deliveryPersonLocation")
                initial_payload = OrderTrackingStreamPayload(
                    order_id=str(order.id),
                    order_status=order.status,
                    estimated_minutes_remaining=order.estimated_minutes_remaining if hasattr(order, "estimated_minutes_remaining") else initial_tracking.get("estimatedMinutes"),
                    estimatedMinutes=initial_tracking.get("estimatedMinutes"),
                    distanceKm=initial_tracking.get("distanceKm"),
                    deliveryPersonLocation=CoordinatesType(
                        type="Point",
                        coordinates=[dp_loc["longitude"], dp_loc["latitude"]]
                    ) if dp_loc else None,
                )

                print(f"[ORDER TRACKING STREAM] Sending initial state")
                yield initial_payload

            except Exception as e:
                print(f"[ORDER TRACKING STREAM] Failed to get initial tracking: {e}")
                # Continue anyway, will get updates from pubsub

            # Listen for updates
            try:
                # Keepalive mechanism - send updates at least every 30 seconds
                last_update_time = asyncio.get_event_loop().time()
                keepalive_interval = 30  # seconds

                while True:
                    try:
                        # Wait for update with timeout for keepalive
                        timeout = keepalive_interval - (asyncio.get_event_loop().time() - last_update_time)
                        if timeout <= 0:
                            timeout = keepalive_interval

                        update = await asyncio.wait_for(queue.get(), timeout=timeout)
                        last_update_time = asyncio.get_event_loop().time()

                        print(f"[ORDER TRACKING STREAM] Received update for order {orderId}")
                        yield update

                    except asyncio.TimeoutError:
                        # Keepalive - re-fetch current state
                        print(f"[ORDER TRACKING STREAM] Keepalive - fetching current state")
                        last_update_time = asyncio.get_event_loop().time()

                        try:
                            current_tracking = await order_service.get_order_tracking(orderId, user_id)
                            current_order = await orders_repo.get_by_id(orderId)

                            if current_order:
                                dp_loc = current_tracking.get("deliveryPersonLocation")
                                keepalive_payload = OrderTrackingStreamPayload(
                                    order_id=str(current_order.id),
                                    order_status=current_order.status,
                                    estimated_minutes_remaining=current_order.estimated_minutes_remaining if hasattr(current_order, "estimated_minutes_remaining") else current_tracking.get("estimatedMinutes"),
                                    estimatedMinutes=current_tracking.get("estimatedMinutes"),
                                    distanceKm=current_tracking.get("distanceKm"),
                                    deliveryPersonLocation=CoordinatesType(
                                        type="Point",
                                        coordinates=[dp_loc["longitude"], dp_loc["latitude"]]
                                    ) if dp_loc else None,
                                )
                                yield keepalive_payload
                        except Exception as e:
                            print(f"[ORDER TRACKING STREAM] Keepalive fetch failed: {e}")
                            # Continue listening
                            continue

            finally:
                await order_pubsub.unsubscribe(f"order_tracking:{orderId}", queue)
                print(f"[ORDER TRACKING STREAM] Unsubscribed from order {orderId}")
                print(f"{'=' * 80}\n")

        except Exception as e:
            print(f"[ORDER TRACKING STREAM] ERROR: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'=' * 80}\n")
            raise
