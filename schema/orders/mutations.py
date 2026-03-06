"""GraphQL mutations for Orders."""

from datetime import datetime, timedelta
from typing import Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from repositories.orders_repository import (
    branch_delivery_requests_repo,
    delivery_persons_repo,
    order_locations_repo,
    orders_repo,
)
from services.orders_service import order_service
from domain.orders import (
    BranchDeliveryRequest,
    DeliveryRequestStatus,
    GeoPoint,
    OrderActor,
    OrderLocationUpdate,
    OrderStatus,
)
from repositories import branches_repo
from utils.graphql_auth import apply_optional_jwt, require_auth

from .inputs import (
    AddOrderCommentInput,
    AssignDeliveryPersonInput,
    CreateOrderInput,
    ModifyOrderItemsInput,
    RequestBranchLinkInput,
    RespondBranchLinkInput,
    UpdateDeliveryLocationInput,
    UpdateOrderStatusInput,
)
from .types import (
    BranchDeliveryRequestType,
    OrderStatusEnum,
    OrderType,
    branch_delivery_request_to_type,
    order_to_type,
)

@strawberry.type
class OrderMutation:
    # Customer mutations
    @strawberry.mutation(description="Crear nuevo pedido")
    async def create_order(
        self, info: Info, input: CreateOrderInput, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.create_order(
                customer_id=user_id,
                branch_id=input.branchId,
                items=[
                    {
                        "itemType": i.itemType.value,
                        "productId": i.productId,
                        "showcaseId": i.showcaseId,
                        "description": i.description,
                        "quantity": i.quantity,
                    }
                    for i in input.items
                ],
                delivery_address={
                    "street": input.deliveryAddress.street,
                    "city": input.deliveryAddress.city,
                    "reference": input.deliveryAddress.reference,
                    "latitude": input.deliveryAddress.latitude,
                    "longitude": input.deliveryAddress.longitude,
                    # Delivery instruction fields (Uber Eats / Glovo style)
                    "addressType": input.deliveryAddress.addressType.value,
                    "buildingName": input.deliveryAddress.buildingName,
                    "floor": input.deliveryAddress.floor,
                    "apartment": input.deliveryAddress.apartment,
                    "deliveryInstructions": input.deliveryAddress.deliveryInstructions,
                },
                payment_method=input.paymentMethod,
                payment_intent_id=input.paymentIntentId,
                promo_code=input.promoCode,
                initial_comment=input.comments,
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Aceptar modificaciones de la tienda")
    async def accept_order_modifications(
        self, info: Info, orderId: str, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.accept_modifications(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Rechazar modificaciones y cancelar pedido")
    async def reject_order_modifications(
        self, info: Info, orderId: str, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.reject_modifications(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Cancelar pedido")
    async def cancel_order(
        self, info: Info, orderId: str, jwt: str, reason: Optional[str] = None
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.cancel_order(orderId, user_id, reason)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Añadir comentario al pedido")
    async def add_order_comment(
        self, info: Info, input: AddOrderCommentInput, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.add_comment(
                input.orderId, user_id, input.message
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Calificar pedido después de entrega")
    async def rate_order(
        self,
        info: Info,
        orderId: str,
        rating: int,
        jwt: str,
        comment: Optional[str] = None,
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.rate_order(orderId, user_id, rating, comment)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    # Business mutations
    @strawberry.mutation(
        description="Aceptar pedido. Si se proporciona deliveryFee, el branch establece manualmente el precio de envío."
    )
    async def accept_order(
        self,
        info: Info,
        orderId: str,
        estimatedMinutes: int,
        jwt: str,
        deliveryFee: Optional[float] = None,
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.accept_order(
                orderId, estimatedMinutes, user_id, delivery_fee_override=deliveryFee
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Rechazar pedido")
    async def reject_order(
        self, info: Info, orderId: str, reason: str, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.reject_order(orderId, reason, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Modificar items del pedido")
    async def modify_order_items(
        self, info: Info, input: ModifyOrderItemsInput, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.modify_order_items(
                input.orderId,
                [
                    {
                        "itemType": i.itemType.value,
                        "productId": i.productId,
                        "showcaseId": i.showcaseId,
                        "description": i.description,
                        "quantity": i.quantity,
                    }
                    for i in input.items
                ],
                input.reason,
                user_id,
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Actualizar estado del pedido")
    async def update_order_status(
        self, info: Info, input: UpdateOrderStatusInput, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.update_status(
                input.orderId,
                OrderStatus(input.status.value),
                OrderActor.BUSINESS,
                input.message,
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Marcar pedido como listo para recoger")
    async def mark_order_ready(self, info: Info, orderId: str, jwt: str) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            order = await order_service.update_status(
                orderId,
                OrderStatus.READY_FOR_PICKUP,
                OrderActor.BUSINESS,
                "Pedido listo para recoger",
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    # Delivery person mutations
    @strawberry.mutation(description="Aceptar pedido para entrega")
    async def accept_delivery(self, info: Info, orderId: str, jwt: str) -> OrderType:
        user_id = require_auth(jwt, info)

        try:
            order = await order_service.accept_delivery(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Confirmar recogida del pedido")
    async def confirm_pickup(self, info: Info, orderId: str, jwt: str) -> OrderType:
        user_id = require_auth(jwt, info)

        try:
            order = await order_service.confirm_pickup(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Actualizar ubicación durante la entrega")
    async def update_delivery_location(
        self, info: Info, input: UpdateDeliveryLocationInput, jwt: str
    ) -> bool:
        user_id = require_auth(jwt, info)

        delivery_person = await delivery_persons_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise Exception("No eres un repartidor registrado")

        # Update delivery person location
        await delivery_persons_repo.update_location(
            delivery_person.id, input.longitude, input.latitude
        )

        # Create location update record
        location_update = OrderLocationUpdate(
            _id=str(ObjectId()),
            orderId=input.orderId,
            deliveryPersonId=delivery_person.id,
            location=GeoPoint(
                type="Point", coordinates=[input.longitude, input.latitude]
            ),
            timestamp=datetime.utcnow(),
            speed=input.speed,
            heading=input.heading,
        )
        await order_locations_repo.create(location_update)

        # Emit tracking event for real-time subscription
        order = await orders_repo.get_by_id(input.orderId)
        if order:
            await order_service._emit_tracking_event(order)

        return True

    @strawberry.mutation(description="Confirmar entrega completada")
    async def confirm_delivery(self, info: Info, orderId: str, jwt: str) -> OrderType:
        user_id = require_auth(jwt, info)

        try:
            order = await order_service.confirm_delivery(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    # Admin mutations
    @strawberry.mutation(description="Asignar repartidor manualmente")
    async def assign_delivery_person(
        self, info: Info, input: AssignDeliveryPersonInput, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Verify admin permissions

        estimated_minutes = input.estimatedMinutes or 30
        estimated_time = datetime.utcnow() + timedelta(minutes=estimated_minutes)

        order = await orders_repo.assign_delivery_person(
            input.orderId, input.deliveryPersonId, estimated_time
        )

        if not order:
            raise Exception("Error al asignar repartidor")

        await delivery_persons_repo.assign_order(input.deliveryPersonId, input.orderId)

        return order_to_type(order)

    # Branch-delivery person link mutations
    @strawberry.mutation(
        description="Solicitar vinculación a una sucursal como repartidor"
    )
    async def request_branch_link(
        self, info: Info, input: RequestBranchLinkInput, jwt: str
    ) -> BranchDeliveryRequestType:
        from schema.orders.queries import _get_or_create_delivery_person

        user_id = require_auth(jwt, info)
        delivery_person = await _get_or_create_delivery_person(user_id)

        # Verify branch exists
        branch = await branches_repo.get_by_id(input.branchId)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Prevent duplicate requests
        existing = await branch_delivery_requests_repo.get_existing(
            delivery_person.id, input.branchId
        )
        if existing:
            if existing.status == DeliveryRequestStatus.PENDING:
                raise Exception("Ya tienes una solicitud pendiente para esta sucursal")
            if existing.status == DeliveryRequestStatus.ACCEPTED:
                raise Exception("Ya estás vinculado a esta sucursal")

        now = datetime.utcnow()
        request = BranchDeliveryRequest(
            _id=str(ObjectId()),
            deliveryPersonId=delivery_person.id,
            branchId=input.branchId,
            status=DeliveryRequestStatus.PENDING,
            message=input.message,
            createdAt=now,
            updatedAt=now,
        )
        created = await branch_delivery_requests_repo.create(request)
        return branch_delivery_request_to_type(created)

    @strawberry.mutation(
        description="Responder a una solicitud de vinculación (manager)"
    )
    async def respond_branch_link_request(
        self, info: Info, input: RespondBranchLinkInput, jwt: str
    ) -> BranchDeliveryRequestType:
        user_id = require_auth(jwt, info)

        req = await branch_delivery_requests_repo.get_by_id(input.requestId)
        if not req:
            raise Exception("Solicitud no encontrada")

        if req.status != DeliveryRequestStatus.PENDING:
            raise Exception("Esta solicitud ya fue respondida")

        # Verify user is a manager of the branch
        branch = await branches_repo.get_by_id(req.branchId)
        if not branch:
            raise Exception("Sucursal no encontrada")
        if str(user_id) not in {str(mid) for mid in branch.managerIds}:
            raise Exception("No tienes permiso para responder esta solicitud")

        new_status = (
            DeliveryRequestStatus.ACCEPTED
            if input.accept
            else DeliveryRequestStatus.REJECTED
        )

        updated_req = await branch_delivery_requests_repo.update_status(
            input.requestId, new_status, user_id
        )

        if input.accept and branch.useAppMessaging:
            await delivery_persons_repo.add_linked_branch(
                req.deliveryPersonId, req.branchId
            )

        return branch_delivery_request_to_type(updated_req)

    @strawberry.mutation(description="Cancelar solicitud de vinculación propia")
    async def cancel_branch_link_request(
        self, info: Info, requestId: str, jwt: str
    ) -> bool:
        from schema.orders.queries import _get_or_create_delivery_person

        user_id = require_auth(jwt, info)
        delivery_person = await _get_or_create_delivery_person(user_id)

        req = await branch_delivery_requests_repo.get_by_id(requestId)
        if not req:
            raise Exception("Solicitud no encontrada")
        if str(req.deliveryPersonId) != str(delivery_person.id):
            raise Exception("No tienes permiso para cancelar esta solicitud")
        if req.status != DeliveryRequestStatus.PENDING:
            raise Exception("Solo se pueden cancelar solicitudes pendientes")

        await branch_delivery_requests_repo.update_status(
            requestId, DeliveryRequestStatus.REJECTED, user_id
        )
        return True

    @strawberry.mutation(description="Forzar cambio de estado (admin)")
    async def force_order_status(
        self, info: Info, orderId: str, status: OrderStatusEnum, reason: str, jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Verify admin permissions

        try:
            order = await order_service.update_status(
                orderId,
                OrderStatus(status.value),
                OrderActor.SYSTEM,
                f"Estado forzado por admin: {reason}",
                force=True,
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
