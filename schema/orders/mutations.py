"""GraphQL mutations for Orders."""
import strawberry
from typing import Optional
from datetime import datetime, timedelta
from strawberry.types import Info
from bson import ObjectId

from .types import OrderType, OrderStatusEnum, order_to_type
from .inputs import (
    CreateOrderInput, UpdateOrderStatusInput, AddOrderCommentInput,
    ModifyOrderItemsInput, UpdateDeliveryLocationInput, AssignDeliveryPersonInput
)
from orders import order_service, orders_repo, delivery_persons_repo, order_locations_repo
from orders.models import OrderStatus, OrderActor, OrderLocationUpdate, GeoPoint
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class OrderMutation:
    # Customer mutations
    @strawberry.mutation(description="Crear nuevo pedido")
    async def create_order(
        self,
        info: Info,
        input: CreateOrderInput,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.create_order(
                customer_id=user_id,
                branch_id=input.branchId,
                items=[{"productId": i.productId, "quantity": i.quantity} for i in input.items],
                delivery_address={
                    "street": input.deliveryAddress.street,
                    "city": input.deliveryAddress.city,
                    "reference": input.deliveryAddress.reference,
                    "latitude": input.deliveryAddress.latitude,
                    "longitude": input.deliveryAddress.longitude
                },
                payment_method=input.paymentMethod,
                payment_intent_id=input.paymentIntentId,
                promo_code=input.promoCode,
                initial_comment=input.comments
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    @strawberry.mutation(description="Aceptar modificaciones de la tienda")
    async def accept_order_modifications(
        self,
        info: Info,
        orderId: str,
        jwt: str
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
        self,
        info: Info,
        orderId: str,
        jwt: str
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
        self,
        info: Info,
        orderId: str,
        jwt: str,
        reason: Optional[str] = None
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
        self,
        info: Info,
        input: AddOrderCommentInput,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.add_comment(input.orderId, user_id, input.message)
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
        comment: Optional[str] = None
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
    @strawberry.mutation(description="Aceptar pedido")
    async def accept_order(
        self,
        info: Info,
        orderId: str,
        estimatedMinutes: int,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.accept_order(orderId, estimatedMinutes, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    @strawberry.mutation(description="Rechazar pedido")
    async def reject_order(
        self,
        info: Info,
        orderId: str,
        reason: str,
        jwt: str
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
        self,
        info: Info,
        input: ModifyOrderItemsInput,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.modify_order_items(
                input.orderId,
                [{"productId": i.productId, "quantity": i.quantity} for i in input.items],
                input.reason,
                user_id
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    @strawberry.mutation(description="Actualizar estado del pedido")
    async def update_order_status(
        self,
        info: Info,
        input: UpdateOrderStatusInput,
        jwt: str
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
                input.message
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    @strawberry.mutation(description="Marcar pedido como listo para recoger")
    async def mark_order_ready(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.update_status(
                orderId,
                OrderStatus.READY_FOR_PICKUP,
                OrderActor.BUSINESS,
                "Pedido listo para recoger"
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    # Delivery person mutations
    @strawberry.mutation(description="Aceptar pedido para entrega")
    async def accept_delivery(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.accept_delivery(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    @strawberry.mutation(description="Confirmar recogida del pedido")
    async def confirm_pickup(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.confirm_pickup(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Actualizar ubicación durante la entrega")
    async def update_delivery_location(
        self,
        info: Info,
        input: UpdateDeliveryLocationInput,
        jwt: str
    ) -> bool:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        delivery_person = await delivery_persons_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise Exception("No eres un repartidor registrado")
        
        # Update delivery person location
        await delivery_persons_repo.update_location(
            delivery_person.id,
            input.longitude,
            input.latitude
        )
        
        # Create location update record
        location_update = OrderLocationUpdate(
            _id=str(ObjectId()),
            orderId=input.orderId,
            deliveryPersonId=delivery_person.id,
            location=GeoPoint(
                type="Point",
                coordinates=[input.longitude, input.latitude]
            ),
            timestamp=datetime.utcnow(),
            speed=input.speed,
            heading=input.heading
        )
        await order_locations_repo.create(location_update)
        
        # TODO: Publish to Redis for real-time updates
        
        return True
    
    @strawberry.mutation(description="Confirmar entrega completada")
    async def confirm_delivery(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        try:
            order = await order_service.confirm_delivery(orderId, user_id)
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
    
    # Admin mutations
    @strawberry.mutation(description="Asignar repartidor manualmente")
    async def assign_delivery_person(
        self,
        info: Info,
        input: AssignDeliveryPersonInput,
        jwt: str
    ) -> OrderType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        # TODO: Verify admin permissions
        
        estimated_minutes = input.estimatedMinutes or 30
        estimated_time = datetime.utcnow() + timedelta(minutes=estimated_minutes)
        
        order = await orders_repo.assign_delivery_person(
            input.orderId,
            input.deliveryPersonId,
            estimated_time
        )
        
        if not order:
            raise Exception("Error al asignar repartidor")
        
        await delivery_persons_repo.assign_order(input.deliveryPersonId, input.orderId)
        
        return order_to_type(order)
    
    @strawberry.mutation(description="Forzar cambio de estado (admin)")
    async def force_order_status(
        self,
        info: Info,
        orderId: str,
        status: OrderStatusEnum,
        reason: str,
        jwt: str
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
                force=True
            )
            return order_to_type(order)
        except ValueError as e:
            raise Exception(str(e))
