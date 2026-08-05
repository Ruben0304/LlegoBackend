"""GraphQL query resolvers for Orders."""

from datetime import datetime
from typing import List, Optional

import strawberry
from bson import ObjectId
from graphql import GraphQLError
from strawberry.types import Info

from core.config import settings
from domain.orders import (
    DeliveryPerson,
    DeliveryRequestStatus,
    OrderStatus,
    VehicleType,
)
from repositories import branches_repo, users_repo
from repositories.orders_repository import (
    branch_delivery_requests_repo,
    delivery_persons_repo,
    orders_repo,
)
from repositories.vehicle_repository import vehicles_repo
from services.delivered_orders_query_service import delivered_orders_query_service
from services.orders_service import order_service
from utils.graphql_auth import apply_optional_jwt, require_auth, require_role

from .inputs import DeliveredOrdersFilterInput
from .types import (
    BranchDeliveryRequestType,
    CoordinatesType,
    CourierPresenceType,
    DashboardStatsType,
    DeliveredOrderFinalStatusEnum,
    DeliveredOrdersConnectionType,
    DeliveredOrdersEdgeType,
    DeliveredOrdersPageInfoType,
    DeliveredOrderType,
    DeliveryFeeEstimateType,
    DeliveryRequestStatusEnum,
    OrdersConnectionType,
    OrderStatsType,
    OrderStatusEnum,
    OrderTrackingType,
    OrderType,
    TopProductType,
    VehicleTypeGQL,
    branch_delivery_request_to_type,
    estimate_delivery_fee,
    order_to_type,
)
from services.courier_presence import get_courier_presence_snapshot


@strawberry.type
class DeliveryPersonStatsType:
    totalDeliveries: int
    totalEarnings: float
    totalDistanceKm: float
    avgDurationMin: float
    avgRating: float



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
        vehicleType=None,
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

    @strawberry.field(
        description=(
            "Pedidos activos (iniciados pero no cancelados ni entregados). "
            "Si se pasa branchId, filtra por esa sucursal; si no, retorna de todas."
        )
    )
    async def active_orders(
        self,
        info: Info,
        jwt: str,
        branchId: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OrdersConnectionType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Verificar permisos (manager/owner/admin) según tu modelo
        orders, total = await orders_repo.get_active(
            branch_id=branchId, limit=limit, offset=offset
        )
        return OrdersConnectionType(
            orders=[order_to_type(o) for o in orders],
            totalCount=total,
            hasMore=(offset + len(orders)) < total,
        )

    @strawberry.field(
        description=(
            "(Admin) Pedidos de toda la plataforma con filtros libres — sin "
            "argumentos requeridos más allá del jwt. Sirve tanto para una cola "
            "'en vivo' (statusIn = estados activos, sin rango de fecha) como "
            "para historial (fromDate/toDate, cualquier status)."
        )
    )
    async def admin_orders(
        self,
        info: Info,
        jwt: str,
        statusIn: Optional[List[str]] = None,
        businessId: Optional[str] = None,
        branchId: Optional[str] = None,
        fromDate: Optional[datetime] = None,
        toDate: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OrdersConnectionType:
        require_role(jwt, info, ["admin", "manager"])

        orders, total = await orders_repo.list_filtered(
            status_in=statusIn,
            business_id=businessId,
            branch_id=branchId,
            from_date=fromDate,
            to_date=toDate,
            limit=limit,
            offset=offset,
        )
        return OrdersConnectionType(
            orders=[order_to_type(o) for o in orders],
            totalCount=total,
            hasMore=(offset + len(orders)) < total,
        )

    @strawberry.field(
        description="(Admin) Tracking de un pedido, sin restricción de propiedad — solo admin/manager"
    )
    async def admin_order_tracking(
        self, info: Info, orderId: str, jwt: str
    ) -> Optional[OrderTrackingType]:
        require_role(jwt, info, ["admin", "manager"])

        try:
            tracking = await order_service.get_order_tracking(
                orderId, user_id="", bypass_authorization=True
            )

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

    @strawberry.field(
        description=(
            "(Admin) Snapshot de mensajeros online y su última ubicación — mismo "
            "dato que alimenta la subscription couriers_presence_stream, pero como "
            "query de una sola vez para sondear por HTTP en vez de WebSocket."
        )
    )
    async def admin_couriers_presence(
        self, info: Info, jwt: str
    ) -> List[CourierPresenceType]:
        require_role(jwt, info, ["admin", "manager"])
        return await get_courier_presence_snapshot()

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
            orders = list(
                await orders_repo.get_awaiting_delivery_acceptance_by_branches(
                    delivery_person.linkedBranchIds
                )
            )
        else:
            orders = list(
                await orders_repo.get_awaiting_delivery_acceptance_nearby(
                    longitude, latitude, radiusKm
                )
            )

        # Always prepend the courier's active delivery (if any) so the map pin
        # never disappears after acceptance — the frontend has ONE source of truth.
        try:
            current = await orders_repo.get_current_delivery(str(delivery_person.id))
            if current is not None:
                existing_ids = {str(o.id) for o in orders}
                if str(current.id) not in existing_ids:
                    orders = [current] + orders
                    print(f"[COURIER] available_orders_for_delivery: prepended active delivery {current.id} status={current.status.value}")
        except Exception as e:
            print(f"[COURIER] available_orders_for_delivery: current delivery lookup failed: {e}")

        return [order_to_type(o) for o in orders]

    @strawberry.field(description="Pedido actual del repartidor")
    async def my_current_delivery(self, info: Info, jwt: str) -> Optional[OrderType]:
        user_id = require_auth(jwt, info)

        delivery_person = await _get_or_create_delivery_person(user_id)

        order = await orders_repo.get_current_delivery(delivery_person.id)
        print(f"[COURIER] my_current_delivery user={user_id} dp={delivery_person.id} order={order.id if order else None} status={order.status.value if order else None}")
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

    @strawberry.field(
        description=(
            "Historial cursor-based de pedidos entregados del repartidor autenticado"
        )
    )
    async def my_delivered_orders(
        self,
        info: Info,
        jwt: str,
        first: int = 20,
        after: Optional[str] = None,
        filter: Optional[DeliveredOrdersFilterInput] = None,
    ) -> DeliveredOrdersConnectionType:
        try:
            user_id = require_auth(jwt, info)
        except Exception as e:
            raise GraphQLError(str(e), extensions={"code": "UNAUTHORIZED"})

        if not settings.courier_delivered_orders_v2_enabled:
            raise GraphQLError(
                "Funcionalidad no habilitada",
                extensions={"code": "FORBIDDEN"},
            )

        delivery_person = await _get_or_create_delivery_person(user_id)

        try:
            result = await delivered_orders_query_service.list_for_courier(
                courier_id=str(delivery_person.id),
                first=first,
                after=after,
                from_date=filter.fromDate if filter else None,
                to_date=filter.toDate if filter else None,
                search=filter.search if filter else None,
                branch_id=filter.branchId if filter else None,
                city=filter.city if filter else None,
                include_fraud_hidden=False,
            )
        except ValueError as e:
            raise GraphQLError(str(e), extensions={"code": "BAD_USER_INPUT"})
        except GraphQLError:
            raise
        except Exception as e:
            raise GraphQLError(str(e), extensions={"code": "FORBIDDEN"})

        return DeliveredOrdersConnectionType(
            edges=[
                DeliveredOrdersEdgeType(
                    cursor=edge["cursor"],
                    node=DeliveredOrderType(
                        orderId=edge["node"]["orderId"],
                        orderNumber=edge["node"]["orderNumber"],
                        deliveredAt=edge["node"]["deliveredAt"],
                        merchantName=edge["node"]["merchantName"],
                        customerDisplayName=edge["node"]["customerDisplayName"],
                        addressSummary=edge["node"]["addressSummary"],
                        city=edge["node"]["city"],
                        visibleAmount=edge["node"]["visibleAmount"],
                        currency=edge["node"]["currency"],
                        finalStatus=DeliveredOrderFinalStatusEnum(
                            edge["node"]["finalStatus"]
                        ),
                        hasDeliveryEvidence=edge["node"]["hasDeliveryEvidence"],
                    ),
                )
                for edge in result["edges"]
            ],
            pageInfo=DeliveredOrdersPageInfoType(
                hasNextPage=result["pageInfo"]["hasNextPage"],
                endCursor=result["pageInfo"]["endCursor"],
            ),
            totalCount=result["totalCount"],
        )

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
        description="Retorna la tasa de cargo de servicio configurada en el servidor (fracción, ej: 0.10 = 10%)"
    )
    def get_service_fee_rate(self) -> float:
        return settings.service_fee_rate

    @strawberry.field(
        description="Tasa de cargo de servicio reducida tras ver videos promocionales (fracción, ej: 0.05 = 5%)"
    )
    def get_discounted_service_fee_rate(self) -> float:
        return settings.discounted_service_fee_rate

    @strawberry.field(
        description="Estadísticas del dashboard: ingresos (subtotal), pedidos completados/rechazados y productos más vendidos dado un rango de fechas"
    )
    async def dashboard_stats(
        self,
        info: Info,
        businessId: str,
        fromDate: datetime,
        toDate: datetime,
        jwt: str,
        branchId: Optional[str] = None,
    ) -> DashboardStatsType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        stats = await orders_repo.get_dashboard_stats(businessId, fromDate, toDate, branchId)

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

    @strawberry.field(description="Pedidos de un cliente específico (admin/manager)")
    async def customer_orders(
        self,
        info: Info,
        user_id: str,
        jwt: str,
        status: Optional[OrderStatusEnum] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OrdersConnectionType:
        require_role(jwt, info, ["admin", "manager"])
        status_filter = OrderStatus(status.value) if status else None
        orders, total = await orders_repo.get_by_customer(
            user_id, status_filter, limit, offset
        )
        return OrdersConnectionType(
            orders=[order_to_type(o) for o in orders],
            totalCount=total,
            hasMore=(offset + len(orders)) < total,
        )


    @strawberry.field(description="Listado de vehículos disponibles para mensajeros")
    async def vehicles(self, info: Info) -> List[VehicleTypeGQL]:
        """Return all active vehicles from the catalog."""
        all_vehicles = await vehicles_repo.get_all(active_only=True)
        return [
            VehicleTypeGQL(
                id=str(v.id),
                name=v.name,
                slug=v.slug.value,
                is_active=v.isActive,
            )
            for v in all_vehicles
        ]
