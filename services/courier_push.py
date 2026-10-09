"""Pushes a la app de choferes (AppMensajeros).

Dos avisos, sobre el mismo `push_service` y el enrutado por bundle que ya usan
clientes y negocios (audiencia `courier`, ver
repositories/device_token_repository.py):

- Al chofer asignado, cuando cambia algo que le afecta y que no hizo él mismo:
  le asignan el pedido (admin), se cancela, el cliente paga, el negocio empieza
  a prepararlo o lo marca listo, o se lo quitan porque el negocio modificó el
  pedido o el cliente lo reenvió a la tienda.
- "Nuevo pedido disponible" a los choferes en línea (presencia en Redis) que
  podrían tomarlo, cuando un pedido pasa a esperar mensajero. No se avisa a
  quien ya tiene una entrega en curso.

Nada de esto rompe ni frena la operación que lo dispara: los errores solo se
loguean y el aviso masivo corre en segundo plano.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from domain.orders import OrderActor, OrderStatus
from services.branch_hours import BRANCH_TIMEZONE
from services.orders_utils import haversine_distance

logger = logging.getLogger(__name__)

# Mismo radio que pide AppMensajeros a availableOrdersForDelivery
# (OrdersRepository.getAvailableOrders, radiusKm = 30).
COURIER_NEW_ORDER_RADIUS_KM = 30.0

PUSH_TYPE_NEW_ORDER = "courier_new_order"
PUSH_TYPE_ORDER_UPDATE = "courier_order_update"

# Estados previos al pago: si el pedido sale de aquí a ACCEPTED es que se pagó.
_AWAITING_PAYMENT = {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_IN_PROGRESS}

# Referencias a las tareas en segundo plano (asyncio solo guarda referencias
# débiles: sin esto el recolector podría cancelarlas a medias).
_background_tasks: Set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Lógica pura
# ---------------------------------------------------------------------------


def format_scheduled_for(scheduled_for: Optional[datetime]) -> Optional[str]:
    """"03/10 14:00" en hora de Cuba. `scheduledFor` se guarda en UTC (naive o aware)."""
    if scheduled_for is None:
        return None
    aware = scheduled_for if scheduled_for.tzinfo else scheduled_for.replace(tzinfo=timezone.utc)
    local = aware.astimezone(ZoneInfo(BRANCH_TIMEZONE))
    return local.strftime("%d/%m %H:%M")


def courier_status_message(
    order_number: str,
    new_status: OrderStatus,
    previous_status: Optional[OrderStatus],
    actor: Optional[OrderActor],
) -> Optional[Tuple[str, str]]:
    """(título, cuerpo) para el chofer asignado, o None si no hay que avisarle.

    Lo que hace el propio chofer (aceptar, recoger, entregar, soltar) no se le
    notifica: ya lo sabe.
    """
    if actor == OrderActor.DELIVERY:
        return None
    if new_status == OrderStatus.CANCELLED:
        return (
            "Pedido cancelado",
            f"El pedido #{order_number} fue cancelado. Ya no tienes que recogerlo ni entregarlo.",
        )
    if new_status == OrderStatus.ACCEPTED and previous_status in _AWAITING_PAYMENT:
        return (
            "Pago confirmado",
            f"El cliente pagó el pedido #{order_number}. El negocio empezará a prepararlo.",
        )
    if new_status == OrderStatus.PREPARING:
        return (
            "Pedido en preparación",
            f"El negocio está preparando el pedido #{order_number}.",
        )
    if new_status == OrderStatus.READY_FOR_PICKUP:
        return (
            "Pedido listo para recoger",
            f"El pedido #{order_number} está listo. Ya puedes pasar a recogerlo.",
        )
    return None


# Motivos por los que se le quita el pedido al chofer sin pasar por update_status.
UNASSIGNED_MODIFIED_BY_STORE = "modified_by_store"
UNASSIGNED_RESUBMITTED = "resubmitted"


def courier_unassigned_message(order_number: str, reason: str) -> Tuple[str, str]:
    """(título, cuerpo) para el chofer al que le acaban de quitar el pedido."""
    if reason == UNASSIGNED_MODIFIED_BY_STORE:
        return (
            "Pedido modificado por el negocio",
            f"El negocio cambió el pedido #{order_number} y el cliente tiene que revisarlo. "
            "Ya no está asignado a ti: no vayas a recogerlo.",
        )
    return (
        "Pedido devuelto a la tienda",
        f"El cliente reenvió el pedido #{order_number} a la tienda. "
        "Ya no está asignado a ti: no vayas a recogerlo.",
    )


def courier_can_take_order(
    linked_branch_ids: Iterable[Any],
    courier_location: Optional[Tuple[float, float]],
    order_branch_id: Any,
    pickup_location: Optional[Tuple[float, float]],
    radius_km: float = COURIER_NEW_ORDER_RADIUS_KM,
) -> bool:
    """¿Vería este chofer el pedido en availableOrdersForDelivery?

    Mismo criterio que la query: un chofer vinculado a sucursales solo ve las
    suyas; uno libre, los cercanos. Sin posición conocida (del chofer o de la
    tienda) se le avisa igual: mejor un aviso de más que perder el pedido.
    Coordenadas como en Mongo: `(longitud, latitud)`.
    """
    linked = {str(b) for b in linked_branch_ids or []}
    if linked:
        return str(order_branch_id) in linked
    if courier_location is None or pickup_location is None:
        return True
    return haversine_distance(courier_location, pickup_location) <= radius_km


def _order_data(order: Any, push_type: str) -> Dict[str, Any]:
    return {
        "type": push_type,
        "orderId": str(order.id),
        "orderNumber": order.orderNumber,
        "status": order.status.value,
    }


def _pickup_location(order: Any) -> Optional[Tuple[float, float]]:
    try:
        coords = order.pickupAddress.coordinates.coordinates
        return (float(coords[0]), float(coords[1]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------


async def send_to_courier_users(
    user_ids: List[str], title: str, body: str, data: Dict[str, Any]
) -> int:
    """Envía a los dispositivos de AppMensajeros de esos usuarios. Devuelve cuántos tokens había."""
    from repositories.device_token_repository import (
        AUDIENCE_COURIER,
        COURIER_IOS_BUNDLE_ID,
        device_token_repo,
    )
    from services.push_notification_service import push_service

    if not user_ids:
        return 0
    tokens = await device_token_repo.get_by_user_ids(user_ids, audience=AUDIENCE_COURIER)
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    android_tokens = [t.token for t in tokens if t.platform == "ANDROID"]
    if ios_tokens:
        await push_service.send_to_all(
            tokens=ios_tokens,
            title=title,
            body=body,
            data=data,
            platform="IOS",
            bundle_id=COURIER_IOS_BUNDLE_ID,
        )
    if android_tokens:
        await push_service.send_to_all(
            tokens=android_tokens, title=title, body=body, data=data, platform="ANDROID"
        )
    return len(ios_tokens) + len(android_tokens)


async def notify_assigned_courier(
    order: Any, title: str, body: str, delivery_person_id: Optional[str] = None
) -> None:
    """Push al chofer asignado al pedido (o al indicado). Nunca lanza."""
    from repositories.orders_repository import delivery_persons_repo

    courier_id = delivery_person_id or getattr(order, "deliveryPersonId", None)
    if not courier_id:
        return
    try:
        courier = await delivery_persons_repo.get_by_id(str(courier_id))
        if not courier:
            return
        sent = await send_to_courier_users(
            [str(courier.userId)], title, body, _order_data(order, PUSH_TYPE_ORDER_UPDATE)
        )
        logger.info("[PUSH COURIER] %s → chofer %s (%s tokens)", title, courier_id, sent)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PUSH COURIER] No se pudo avisar al chofer %s: %s", courier_id, exc)


async def notify_courier_assigned_by_admin(order: Any) -> None:
    """Un admin asignó el pedido a un chofer (assignDeliveryPerson)."""
    scheduled = format_scheduled_for(getattr(order, "scheduledFor", None))
    body = f"Te asignaron el pedido #{order.orderNumber}."
    if scheduled:
        body += f" Programado para {scheduled}."
    await notify_assigned_courier(order, "Nuevo pedido asignado", body)


async def notify_courier_unassigned(order: Any, delivery_person_id: str, reason: str) -> None:
    """Al pedido le quitaron el chofer fuera de update_status (modify_order_items,
    resubmit_order): el pedido ya llega sin chofer, así que se pasa aparte.
    Nunca lanza."""
    if not delivery_person_id:
        return
    title, body = courier_unassigned_message(order.orderNumber, reason)
    await notify_assigned_courier(order, title, body, delivery_person_id=str(delivery_person_id))


async def notify_status_change(
    before: Any,
    updated: Any,
    actor: Optional[OrderActor],
    released_by_delivery_person_id: Optional[str] = None,
) -> None:
    """Punto de entrada desde OrderService al cambiar de estado. Nunca lanza.

    `released_by_delivery_person_id`: chofer que acaba de soltar el pedido. En
    reject_order_for_payment el pedido llega ya sin chofer (`before` se lee
    después de clear_delivery_person), así que hay que pasarlo aparte.
    """
    try:
        if (
            updated.status == OrderStatus.AWAITING_DELIVERY_ACCEPTANCE
            and not updated.deliveryPersonId
        ):
            # Si un chofer lo acaba de soltar, a él no se le ofrece otra vez.
            exclude = set()
            if before is not None and before.deliveryPersonId:
                exclude.add(str(before.deliveryPersonId))
            if released_by_delivery_person_id:
                exclude.add(str(released_by_delivery_person_id))
            spawn(broadcast_new_order(updated, exclude_delivery_person_ids=exclude))
            return

        courier_id = updated.deliveryPersonId or (before.deliveryPersonId if before else None)
        if not courier_id:
            return
        message = courier_status_message(
            updated.orderNumber, updated.status, before.status if before else None, actor
        )
        if message:
            await notify_assigned_courier(updated, *message, delivery_person_id=str(courier_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[PUSH COURIER] Falló el aviso del pedido %s: %s", getattr(updated, "id", "?"), exc
        )


async def broadcast_new_order(order: Any, exclude_delivery_person_ids: Iterable[str] = ()) -> int:
    """"Nuevo pedido disponible" a los choferes en línea que podrían tomarlo.

    Quien ya tiene una entrega en curso no cuenta: la app trabaja con una sola
    entrega a la vez (myCurrentDelivery) y avisarle mientras reparte es ruido.
    Tampoco quien no tiene vehículo vinculado, porque no podría aceptarlo.
    Devuelve a cuántos choferes se avisó. Nunca lanza.
    """
    from repositories import branches_repo
    from repositories.orders_repository import delivery_persons_repo, orders_repo
    from services.courier_presence import fetch_online_couriers_sync

    try:
        if getattr(order, "deliveryMode", None) in ("pickup", "pickup_only"):
            return 0
        branch = await branches_repo.get_by_id(str(order.branchId))
        if branch is not None and getattr(branch, "isDemoStore", False):
            # La tienda demo (revisión de Apple) se autogestiona: no molestar a choferes reales.
            return 0

        online = await asyncio.to_thread(fetch_online_couriers_sync)
        excluded = {str(i) for i in exclude_delivery_person_ids}
        candidate_ids = [cid for cid in online if cid not in excluded]
        if not candidate_ids:
            return 0

        couriers = await delivery_persons_repo.get_by_ids(candidate_ids)
        busy = await orders_repo.get_delivery_person_ids_with_active_order(
            [str(c.id) for c in couriers]
        )
        pickup = _pickup_location(order)
        user_ids = []
        for courier in couriers:
            if not getattr(courier, "isActive", True) or str(courier.id) in busy:
                continue
            # Sin vehículo no puede aceptarlo (VEHICLE_REQUIRED_MESSAGE): avisarle es ruido.
            if not getattr(courier, "vehicleType", None):
                continue
            location = online.get(str(courier.id))
            if location is None and courier.currentLocation:
                coords = courier.currentLocation.coordinates
                location = (float(coords[0]), float(coords[1]))
            if courier_can_take_order(courier.linkedBranchIds, location, order.branchId, pickup):
                user_ids.append(str(courier.userId))
        if not user_ids:
            return 0

        branch_name = getattr(branch, "name", None)
        body = f"Pedido #{order.orderNumber}"
        if branch_name:
            body += f" en {branch_name}"
        scheduled = format_scheduled_for(getattr(order, "scheduledFor", None))
        body += f", programado para {scheduled}." if scheduled else ". Tócalo para verlo."
        await send_to_courier_users(
            user_ids, "Nuevo pedido disponible", body, _order_data(order, PUSH_TYPE_NEW_ORDER)
        )
        logger.info("[PUSH COURIER] Pedido %s ofrecido a %s choferes", order.id, len(user_ids))
        return len(user_ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[PUSH COURIER] Falló el aviso de nuevo pedido %s: %s", getattr(order, "id", "?"), exc
        )
        return 0


def spawn(coro) -> None:
    """Lanza `coro` en segundo plano sin perder la referencia."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
