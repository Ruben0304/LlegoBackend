"""GraphQL subscriptions for real-time order updates."""
import strawberry
from typing import AsyncGenerator, NoReturn, Optional, List
import asyncio
import logging

from strawberry.types import Info
from services.access_checker import access_checker
from utils.graphql_auth import require_auth

from .types import (
    OrderType,
    DeliveryLocationUpdateType,
    CoordinatesType,
    OrderTrackingStreamPayload,
    CourierPresenceType,
    order_to_type,
)
from repositories.orders_repository import orders_repo, delivery_persons_repo
from services.access_checker import access_checker
from services.courier_presence import (
    enrich_courier_snapshot as _enrich_courier_snapshot,
    fetch_courier_presence_snapshot_sync as _redis_fetch_courier_presence_snapshot_sync,
)
from services.orders_service import order_service
from bson import ObjectId

logger = logging.getLogger(__name__)


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
    """Publish a new (or resubmitted) order to branch subscribers (newBranchOrder)."""
    await order_pubsub.publish(f"branch:{branch_id}", order)


async def publish_branch_order_update(branch_id: str, order):
    """Publish an order status/payment change to branch subscribers (branchOrderUpdated)."""
    await order_pubsub.publish(f"branch_updates:{branch_id}", order)


async def publish_delivery_location(order_id: str, location_update: dict):
    """Publish delivery location update."""
    await order_pubsub.publish(f"delivery_location:{order_id}", location_update)


async def publish_order_tracking(order_id: str, tracking_data: OrderTrackingStreamPayload):
    """Publish order tracking update for streaming subscription."""
    await order_pubsub.publish(f"order_tracking:{order_id}", tracking_data)


# ---------------------------------------------------------------------------
# Autorizacion de subscriptions
#
# Como en queries y mutations, no hay middleware: cada subscription comprueba
# quien escucha antes de suscribirse al canal. Sin esto cualquiera con un
# orderId/branchId podia seguir la ubicacion del mensajero o los pedidos de una
# sucursal ajena (context.md §12.5).
# ---------------------------------------------------------------------------

# Staff de plataforma: mismo criterio que adminCouriersPresence/adminOrderTracking.
PLATFORM_STAFF_ROLES = ("admin", "manager")


class SubscriptionAuthRequired(Exception):
    """Quien se suscribe no manda jwt y el contexto no trae usuario."""


def _context_user(info: Info) -> tuple[Optional[str], Optional[str]]:
    context = info.context
    if isinstance(context, dict):
        return context.get("user_id"), context.get("user_role")
    return getattr(context, "user_id", None), getattr(context, "user_role", None)


def _authenticate_subscription(info: Info, jwt: Optional[str]) -> tuple[str, Optional[str]]:
    """(user_id, rol) de quien se suscribe: del contexto (connection_init) o del
    parametro jwt. Lanza si no hay un JWT valido."""
    user_id, user_role = _context_user(info)
    if not user_id and jwt:
        require_auth(jwt, info)
        user_id, user_role = _context_user(info)
    if not user_id:
        raise SubscriptionAuthRequired("Autenticación requerida. Proporciona un JWT válido.")
    return user_id, user_role


async def _require_order_subscription_access(info: Info, jwt: Optional[str], order_id: str):
    """Cliente dueno, personal de la sucursal, mensajero asignado o staff de
    plataforma (OrderService.user_can_access_order). Devuelve el pedido."""
    user_id, user_role = _authenticate_subscription(info, jwt)
    order = await orders_repo.get_by_id(order_id)
    if not order:
        raise Exception("Pedido no encontrado")
    if not await order_service.user_can_access_order(order, user_id, user_role):
        raise Exception("No autorizado")
    return order


async def _require_branch_subscription_access(info: Info, jwt: Optional[str], branch_id: str) -> None:
    """Dueno o manager de la sucursal (access_checker) o staff de plataforma."""
    user_id, user_role = _authenticate_subscription(info, jwt)
    if user_role in PLATFORM_STAFF_ROLES:
        return
    has_access, error_message = await access_checker.check_branch_access(user_id, branch_id)
    if not has_access:
        raise Exception(error_message or "No autorizado")


# ---------------------------------------------------------------------------
# Denegar sin provocar bucles de reconexion
#
# LlegoBusiness (version actual) abre newBranchOrder, branchOrderUpdated y
# deliveryLocationUpdated sin jwt, y SubscriptionManager.collectWithReconnect se
# vuelve a suscribir AL INSTANTE cuando el stream termina sin excepcion (Apollo
# Kotlin 4 entrega el error como respuesta y completa el flow). Si el servidor
# cerrara el stream al denegar, cada sucursal y dispositivo entraria en un bucle
# de reconexion a velocidad de RTT, con un traceback por intento en el log.
# Por eso, en esas subscriptions y en orderUpdated:
#   - Sin credenciales (ni jwt ni usuario en el contexto): el stream queda
#     abierto sin emitir nada hasta que el cliente lo cierre; un warning al abrir.
#   - JWT invalido, pedido inexistente o sin acceso: se espera
#     SUBSCRIPTION_DENIED_DELAY_SECONDS antes de devolver el error, asi un
#     cliente que reintenta sin pausa lo hace como mucho una vez por intervalo.
# En ningun caso se llega a escuchar el canal.
# ---------------------------------------------------------------------------

SUBSCRIPTION_DENIED_DELAY_SECONDS = 30.0


async def _hold_or_reject_subscription(name: str, target_id: str, error: Exception) -> NoReturn:
    if isinstance(error, SubscriptionAuthRequired):
        logger.warning(
            "Subscription %s(%s) sin jwt: queda abierta sin emitir eventos hasta que "
            "el cliente la cierre",
            name,
            target_id,
        )
        await asyncio.Event().wait()  # Nunca se activa: solo sale si se cancela.
    logger.warning("Subscription %s(%s) denegada: %s", name, target_id, error)
    await asyncio.sleep(SUBSCRIPTION_DENIED_DELAY_SECONDS)
    raise error


async def _guard_order_subscription(
    name: str, info: Info, jwt: Optional[str], order_id: str
) -> None:
    try:
        await _require_order_subscription_access(info, jwt, order_id)
    except Exception as exc:
        await _hold_or_reject_subscription(name, order_id, exc)


async def _guard_branch_subscription(
    name: str, info: Info, jwt: Optional[str], branch_id: str
) -> None:
    try:
        await _require_branch_subscription_access(info, jwt, branch_id)
    except Exception as exc:
        await _hold_or_reject_subscription(name, branch_id, exc)


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
        # Ubicacion de TODOS los mensajeros: solo staff de plataforma, igual
        # que la query adminCouriersPresence. Antes bastaba cualquier JWT.
        _, user_role = _authenticate_subscription(info, jwt)
        if user_role not in PLATFORM_STAFF_ROLES:
            raise Exception(
                f"Acceso denegado. Se requiere rol: {', '.join(PLATFORM_STAFF_ROLES)}"
            )

        # Guard interval
        effective_interval = max(0.5, float(intervalSeconds or 2.0))

        while True:
            snapshot = await asyncio.to_thread(_redis_fetch_courier_presence_snapshot_sync)
            snapshot = await _enrich_courier_snapshot(snapshot)
            yield snapshot
            await asyncio.sleep(effective_interval)

    @strawberry.subscription(description="Escuchar cambios en un pedido específico")
    async def order_updated(
        self, info: Info, orderId: str, jwt: Optional[str] = None
    ) -> AsyncGenerator[OrderType, None]:
        """Subscribe to order updates."""
        await _guard_order_subscription("orderUpdated", info, jwt, orderId)
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
        info: Info,
        orderId: str,
        jwt: Optional[str] = None,
    ) -> AsyncGenerator[DeliveryLocationUpdateType, None]:
        """Subscribe to delivery location updates."""
        await _guard_order_subscription("deliveryLocationUpdated", info, jwt, orderId)
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
    
    @strawberry.subscription(
        description=(
            "Nuevos pedidos para una sucursal (también los reenviados por el "
            "cliente). Requiere jwt con acceso a la sucursal; sin jwt no emite."
        )
    )
    async def new_branch_order(
        self, info: Info, branchId: str, jwt: Optional[str] = None
    ) -> AsyncGenerator[OrderType, None]:
        """Subscribe to new orders for a branch."""
        await _guard_branch_subscription("newBranchOrder", info, jwt, branchId)
        queue = await order_pubsub.subscribe(f"branch:{branchId}")
        try:
            while True:
                order = await queue.get()
                yield order_to_type(order)
        finally:
            await order_pubsub.unsubscribe(f"branch:{branchId}", queue)
    
    @strawberry.subscription(
        description=(
            "Cambios de estado o de pago en pedidos de una sucursal. Requiere "
            "jwt con acceso a la sucursal; sin jwt no emite."
        )
    )
    async def branch_order_updated(
        self, info: Info, branchId: str, jwt: Optional[str] = None
    ) -> AsyncGenerator[OrderType, None]:
        """Subscribe to order updates for a branch."""
        await _guard_branch_subscription("branchOrderUpdated", info, jwt, branchId)
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
            try:
                user_id, user_role = _authenticate_subscription(info, jwt)
            except Exception as e:
                print(f"[ORDER TRACKING STREAM] Authentication failed: {e}")
                print(f"{'=' * 80}\n")
                raise Exception("Autenticación requerida. Proporciona un JWT válido en connection_init o como parámetro jwt.")

            print(f"[ORDER TRACKING STREAM] User authenticated: {user_id}")

            # Verify order access: cliente dueno, personal de la sucursal,
            # mensajero asignado o staff de plataforma. Antes solo se comprobaba
            # que el pedido existiera y cualquiera podia seguir uno ajeno.
            order = await orders_repo.get_by_id(orderId)
            if not order:
                print(f"[ORDER TRACKING STREAM] Order not found: {orderId}")
                print(f"{'=' * 80}\n")
                raise Exception("Pedido no encontrado")

            if not await order_service.user_can_access_order(order, user_id, user_role):
                print(f"[ORDER TRACKING STREAM] Access denied for user {user_id} on order {orderId}")
                print(f"{'=' * 80}\n")
                raise Exception("No autorizado")

            print(f"[ORDER TRACKING STREAM] Order found, subscribing to updates...")

            # Subscribe to tracking channel
            queue = await order_pubsub.subscribe(f"order_tracking:{orderId}")

            # Send initial state immediately. El acceso ya se verifico arriba con
            # user_can_access_order (que ademas admite staff de plataforma), por
            # eso no se repite la comprobacion de get_order_tracking.
            try:
                initial_tracking = await order_service.get_order_tracking(
                    orderId, user_id, bypass_authorization=True
                )

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
                            current_tracking = await order_service.get_order_tracking(
                                orderId, user_id, bypass_authorization=True
                            )
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
