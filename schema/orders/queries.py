"""GraphQL query resolvers for Orders."""

from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from repositories.orders_repository import (
    branch_delivery_requests_repo,
    delivery_persons_repo,
    orders_repo,
)
from services.orders_service import order_service
from domain.orders import (
    DeliveryPerson,
    DeliveryRequestStatus,
    OrderStatus,
    VehicleType,
)
from repositories import branches_repo, users_repo
from utils.graphql_auth import apply_optional_jwt, require_auth

from .types import (
    BranchDeliveryRequestType,
    CoordinatesType,
    DashboardStatsType,
    DeliveryFeeEstimateType,
    DeliveryRequestStatusEnum,
    OrdersConnectionType,
    OrderStatsType,
    OrderStatusEnum,
    OrderTrackingType,
    OrderType,
    TopProductType,
    branch_delivery_request_to_type,
    estimate_delivery_fee,
    order_to_type,
)

@strawberry.type
class DeliveryPersonStatsType:
    totalDeliveries: int
    totalEarnings: float
    totalDistanceKm: float
    avgDurationMin: float
    avgRating: float

@strawberry.enum
class DashboardPeriod(Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"


async def _get_or_create_delivery_person(user_id: str) -> DeliveryPerson:
    """Get existing delivery person or create one from user profile."""
    delivery_person = await delivery_persons_repo.get_by_user_id(user_id)
    if delivery_person:
        return delivery_person

    user = await users_repo.get_by_id(user_id)
    if not user:
        raise Exception("Usuario no encontrado")

    now = datetime.utcnow()
    new_dp = DeliveryPerson(
        _id=str(ObjectId()),
        userId=user_id,
        name=user.name or "",
        phone=user.phone,
        vehicleType=VehicleType.A_PIE,
        createdAt=now,
        updatedAt=now,
    )
    return await delivery_persons_repo.create(new_dp)

@strawberry.type
class OrderQuery:
    @strawberry.field(description="Obtener mis pedidos con paginación")
    async def my_orders(
        self,
        info: Info,
        jwt: str,
        status: Optional[OrderStatusEnum] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> OrdersConnectionType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        status_filter = OrderStatus(status.value) if status else None
        orders, total = await orders_repo.get_by_customer(
            user_id, status_filter, limit, offset
        )

        return OrdersConnectionType(
            orders=[order_to_type(o) for o in orders],
            totalCount=total,
            hasMore=(offset + len(orders)) < total,
        )

    @strawberry.field(description="Obtener un pedido por ID")
    async def order(self, info: Info, id: str, jwt: str) -> Optional[OrderType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        order = await orders_repo.get_by_id(id)
        if not order:
            return None

        # Verify access (customer, business owner, branch manager, or delivery person)
        # For simplicity, just return if user is customer
        # Full authorization should check all roles
        if str(order.customerId) != str(user_id):
            # TODO: Check if user is business owner, branch manager, or delivery person
            pass

        return order_to_type(order)

    @strawberry.field(description="Obtener pedido por número de orden")
    async def order_by_number(
        self, info: Info, orderNumber: str, jwt: str
    ) -> Optional[OrderType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        order = await orders_repo.get_by_order_number(orderNumber)
        if not order:
            return None

        return order_to_type(order)

    @strawberry.field(description="Tracking completo de un pedido")
    async def order_tracking(
        self, info: Info, orderId: str, jwt: str
    ) -> Optional[OrderTrackingType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            tracking = await order_service.get_order_tracking(orderId, user_id)

            store_loc = tracking["storeLocation"]
            delivery_loc = tracking["deliveryLocation"]
            dp_loc = tracking.get("deliveryPersonLocation")

            return OrderTrackingType(
                order=order_to_type(tracking["order"]),
                storeLocation=CoordinatesType(
                    type="Point",
                    coordinates=[store_loc["longitude"], store_loc["latitude"]],
                ),
                deliveryLocation=CoordinatesType(
                    type="Point",
                    coordinates=[delivery_loc["longitude"], delivery_loc["latitude"]],
                ),
                deliveryPersonLocation=CoordinatesType(
                    type="Point", coordinates=[dp_loc["longitude"], dp_loc["latitude"]]
                )
                if dp_loc
                else None,
                estimatedMinutes=tracking.get("estimatedMinutes"),
                distanceKm=tracking.get("distanceKm"),
            )
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(description="Pedidos de una sucursal")
    async def branch_orders(
        self,
        info: Info,
        branchId: str,
        jwt: str,
        status: Optional[OrderStatusEnum] = None,
        fromDate: Optional[datetime] = None,
        toDate: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OrdersConnectionType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Verify user is branch manager or business owner

        status_filter = OrderStatus(status.value) if status else None
        orders, total = await orders_repo.get_by_branch(
            branchId, status_filter, fromDate, toDate, limit, offset
        )

        return OrdersConnectionType(
            orders=[order_to_type(o) for o in orders],
            totalCount=total,
            hasMore=(offset + len(orders)) < total,
        )

    @strawberry.field(description="Pedidos pendientes de una sucursal")
    async def pending_branch_orders(
        self, info: Info, branchId: str, jwt: str
    ) -> List[OrderType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        orders = await orders_repo.get_pending_by_branch(branchId)
        return [order_to_type(o) for o in orders]

    @strawberry.field(description="Pedidos disponibles para repartidores cerca")
    async def available_orders_for_delivery(
        self,
        info: Info,
        latitude: float,
        longitude: float,
        jwt: str,
        radiusKm: float = 5.0,
    ) -> List[OrderType]:
        user_id = require_auth(jwt, info)

        delivery_person = await _get_or_create_delivery_person(user_id)

        if delivery_person.linkedBranchIds:
            orders = await orders_repo.get_ready_for_pickup_by_branches(
                delivery_person.linkedBranchIds
            )
        else:
            orders = await orders_repo.get_ready_for_pickup_nearby(
                longitude, latitude, radiusKm
            )

        return [order_to_type(o) for o in orders]

    @strawberry.field(description="Pedido actual del repartidor")
    async def my_current_delivery(self, info: Info, jwt: str) -> Optional[OrderType]:
        user_id = require_auth(jwt, info)

        delivery_person = await _get_or_create_delivery_person(user_id)

        order = await orders_repo.get_current_delivery(delivery_person.id)
        return order_to_type(order) if order else None

    @strawberry.field(description="Historial de pedidos del repartidor autenticado")
    async def my_deliveries(
        self,
        info: Info,
        jwt: str,
        status: Optional[OrderStatusEnum] = None,
        page: int = 1,
        pageSize: int = 20,
    ) -> List[OrderType]:
        user_id = require_auth(jwt, info)

        delivery_person = await _get_or_create_delivery_person(user_id)

        status_filter = status.value if status else None
        orders = await orders_repo.get_by_delivery_person(
            delivery_person.id, page, pageSize, status_filter
        )
        return [order_to_type(o) for o in orders]

    @strawberry.field(description="Estadísticas del repartidor autenticado")
    async def my_delivery_stats(self, info: Info, jwt: str) -> DeliveryPersonStatsType:
        user_id = require_auth(jwt, info)

        delivery_person = await _get_or_create_delivery_person(user_id)

        stats = await orders_repo.get_delivery_person_stats(delivery_person.id)
        return DeliveryPersonStatsType(
            totalDeliveries=stats["totalDeliveries"],
            totalEarnings=stats["totalEarnings"],
            totalDistanceKm=stats["totalDistanceKm"],
            avgDurationMin=stats["avgDurationMin"],
            avgRating=stats["avgRating"],
        )

    @strawberry.field(description="Mis solicitudes de vinculación a sucursales")
    async def my_branch_link_requests(
        self,
        info: Info,
        jwt: str,
        status: Optional[DeliveryRequestStatusEnum] = None,
    ) -> List[BranchDeliveryRequestType]:
        user_id = require_auth(jwt, info)
        delivery_person = await _get_or_create_delivery_person(user_id)

        status_filter = DeliveryRequestStatus(status.value) if status else None
        requests = await branch_delivery_requests_repo.get_by_delivery_person(
            delivery_person.id, status_filter
        )
        return [branch_delivery_request_to_type(r) for r in requests]

    @strawberry.field(
        description="Solicitudes de vinculación a una sucursal (para managers)"
    )
    async def branch_link_requests(
        self,
        info: Info,
        branchId: str,
        jwt: str,
        status: Optional[DeliveryRequestStatusEnum] = None,
    ) -> List[BranchDeliveryRequestType]:
        user_id = require_auth(jwt, info)

        branch = await branches_repo.get_by_id(branchId)
        if not branch:
            raise Exception("Sucursal no encontrada")
        if str(user_id) not in {str(mid) for mid in branch.managerIds}:
            raise Exception("No tienes permiso para ver estas solicitudes")

        status_filter = DeliveryRequestStatus(status.value) if status else None
        requests = await branch_delivery_requests_repo.get_by_branch(
            branchId, status_filter
        )
        return [branch_delivery_request_to_type(r) for r in requests]

    @strawberry.field(description="Estadísticas de pedidos")
    async def order_stats(
        self,
        info: Info,
        fromDate: datetime,
        toDate: datetime,
        jwt: str,
        branchId: Optional[str] = None,
    ) -> OrderStatsType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Verify user has admin access

        stats = await orders_repo.get_stats(branchId, fromDate, toDate)

        return OrderStatsType(
            totalOrders=stats["totalOrders"],
            completedOrders=stats["completedOrders"],
            cancelledOrders=stats["cancelledOrders"],
            totalRevenue=stats["totalRevenue"],
            averageOrderValue=stats["averageOrderValue"],
            averageDeliveryTime=stats["averageDeliveryTime"],
        )

    @strawberry.field(
        description="Estimar precio de envío antes de crear el pedido. Usa la ubicación guardada del usuario autenticado."
    )
    async def estimate_delivery_fee(
        self,
        info: Info,
        branchId: str,
        jwt: str,
        subtotal: float = 0.0,
    ) -> DeliveryFeeEstimateType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        if not user.location or not user.location.get("coordinates"):
            raise Exception(
                "No tienes una ubicación guardada. Actualiza tu ubicación para estimar el envío."
            )

        coords = user.location["coordinates"]  # [lon, lat]
        longitude = coords[0]
        latitude = coords[1]

        try:
            return await estimate_delivery_fee(
                branch_id=branchId,
                latitude=latitude,
                longitude=longitude,
                subtotal=subtotal,
            )
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(
        description="Estadísticas del dashboard: ingresos, pedidos completados/rechazados y productos más vendidos por período (today, week, month)"
    )
    async def dashboard_stats(
        self,
        info: Info,
        businessId: str,
        period: DashboardPeriod,
        jwt: str,
    ) -> DashboardStatsType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == DashboardPeriod.TODAY:
            from_date = today_start
        elif period == DashboardPeriod.WEEK:
            from_date = today_start - timedelta(days=today_start.weekday())
        else:  # MONTH
            from_date = today_start.replace(day=1)

        to_date = now

        stats = await orders_repo.get_dashboard_stats(businessId, from_date, to_date)

        return DashboardStatsType(
            totalRevenue=stats["totalRevenue"],
            completedOrders=stats["completedOrders"],
            cancelledOrders=stats["cancelledOrders"],
            topProducts=[
                TopProductType(
                    productId=str(p["productId"]),
                    name=p["name"],
                    _image_path=p["imageUrl"],
                    totalQuantity=p["totalQuantity"],
                    totalRevenue=p["totalRevenue"],
                )
                for p in stats["topProducts"]
            ],
        )
