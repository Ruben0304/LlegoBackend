"""Order service with business logic."""
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import uuid

from .models import (
    Order, OrderItem, OrderDiscount, DeliveryAddress, OrderTimeline,
    OrderComment, OrderStatus, PaymentStatus, DiscountType, OrderActor,
    GeoPoint, ALLOWED_TRANSITIONS
)
from .repository import OrderRepository, DeliveryPersonRepository, OrderLocationRepository
from .utils import generate_order_number, calculate_delivery_fee, haversine_distance
from repositories import products_repo, branches_repo, businesses_repo, users_repo


class OrderService:
    """Service for order business logic."""
    
    def __init__(self):
        self.orders_repo = OrderRepository()
        self.delivery_repo = DeliveryPersonRepository()
        self.locations_repo = OrderLocationRepository()
    
    async def create_order(
        self,
        customer_id: str,
        branch_id: str,
        items: List[dict],  # [{"productId": str, "quantity": int}]
        delivery_address: dict,
        payment_method: str,
        payment_intent_id: Optional[str] = None,
        promo_code: Optional[str] = None,
        initial_comment: Optional[str] = None
    ) -> Order:
        """Create a new order with all validations."""
        # 1. Validate branch exists and is active
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise ValueError("Sucursal no encontrada")
        if branch.status != "active":
            raise ValueError("La sucursal no está activa")
        
        # 2. Get business
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            raise ValueError("Negocio no encontrado")
        
        # 3. Validate and snapshot products
        order_items: List[OrderItem] = []
        subtotal = 0.0
        
        for item in items:
            product = await products_repo.get_by_id(item["productId"])
            if not product:
                raise ValueError(f"Producto {item['productId']} no encontrado")
            if not product.availability:
                raise ValueError(f"Producto {product.name} no disponible")
            if product.branchId != branch_id:
                raise ValueError(f"Producto {product.name} no pertenece a esta sucursal")
            
            order_item = OrderItem(
                productId=product.id,
                name=product.name,
                price=product.price,
                quantity=item["quantity"],
                imageUrl=product.image,
                wasModifiedByStore=False
            )
            order_items.append(order_item)
            subtotal += product.price * item["quantity"]

        # 4. Calculate delivery fee
        branch_coords = (
            branch.coordinates.coordinates[0],
            branch.coordinates.coordinates[1]
        )
        delivery_coords = (
            delivery_address["longitude"],
            delivery_address["latitude"]
        )
        delivery_fee = calculate_delivery_fee(branch_coords, delivery_coords)
        
        # 5. Apply discounts
        discounts: List[OrderDiscount] = []
        customer = await users_repo.get_by_id(customer_id)
        
        # Premium discount (example - 10% off)
        # TODO: Check if user has premium subscription
        
        # Promo code discount
        if promo_code:
            # TODO: Validate promo code and apply discount
            pass
        
        total_discounts = sum(d.amount for d in discounts)
        total = round(subtotal + delivery_fee - total_discounts, 2)
        
        # 6. Validate payment if card
        payment_status = PaymentStatus.PENDING
        if payment_method == "card":
            if not payment_intent_id:
                raise ValueError("Se requiere paymentIntentId para pagos con tarjeta")
            # TODO: Verify payment intent with Stripe
            payment_status = PaymentStatus.VALIDATED
        
        # 7. Create order
        now = datetime.utcnow()
        order_id = str(ObjectId())
        order_number = await generate_order_number()
        
        delivery_addr = DeliveryAddress(
            street=delivery_address["street"],
            city=delivery_address.get("city"),
            reference=delivery_address.get("reference"),
            coordinates=GeoPoint(
                type="Point",
                coordinates=[delivery_address["longitude"], delivery_address["latitude"]]
            )
        )
        
        timeline = [OrderTimeline(
            status=OrderStatus.PENDING_ACCEPTANCE,
            timestamp=now,
            message="Pedido creado, esperando confirmación de la tienda",
            actor=OrderActor.SYSTEM
        )]
        
        comments = []
        if initial_comment:
            comments.append(OrderComment(
                id=str(uuid.uuid4()),
                author=OrderActor.CUSTOMER,
                message=initial_comment,
                timestamp=now
            ))
        
        order = Order(
            _id=order_id,
            orderNumber=order_number,
            customerId=customer_id,
            branchId=branch_id,
            businessId=business.id,
            items=order_items,
            subtotal=round(subtotal, 2),
            deliveryFee=delivery_fee,
            discounts=discounts,
            total=total,
            currency="USD",
            status=OrderStatus.PENDING_ACCEPTANCE,
            deliveryAddress=delivery_addr,
            timeline=timeline,
            comments=comments,
            paymentMethod=payment_method,
            paymentStatus=payment_status,
            paymentId=payment_intent_id,
            createdAt=now,
            updatedAt=now,
            lastStatusAt=now
        )
        
        created_order = await self.orders_repo.create(order)
        
        # 8. TODO: Send push notification to branch
        
        return created_order

    def _validate_transition(
        self,
        current_status: OrderStatus,
        new_status: OrderStatus
    ) -> bool:
        """Validate if status transition is allowed."""
        allowed = ALLOWED_TRANSITIONS.get(current_status.value, [])
        return new_status.value in allowed
    
    async def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        actor: OrderActor,
        message: Optional[str] = None,
        force: bool = False
    ) -> Order:
        """Update order status with validation."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if not force and not self._validate_transition(order.status, new_status):
            raise ValueError(
                f"Transición de estado no permitida: {order.status.value} -> {new_status.value}"
            )
        
        # Default messages
        if not message:
            messages = {
                OrderStatus.ACCEPTED: "Pedido aceptado por la tienda",
                OrderStatus.PREPARING: "Tu pedido está siendo preparado",
                OrderStatus.READY_FOR_PICKUP: "Pedido listo para recoger",
                OrderStatus.ON_THE_WAY: "Tu pedido está en camino",
                OrderStatus.DELIVERED: "Pedido entregado",
                OrderStatus.CANCELLED: "Pedido cancelado",
                OrderStatus.MODIFIED_BY_STORE: "La tienda ha modificado tu pedido"
            }
            message = messages.get(new_status, f"Estado actualizado a {new_status.value}")
        
        timeline_entry = OrderTimeline(
            status=new_status,
            timestamp=datetime.utcnow(),
            message=message,
            actor=actor
        )
        
        updated_order = await self.orders_repo.update_status(
            order_id, new_status, timeline_entry
        )
        
        if not updated_order:
            raise ValueError("Error al actualizar el pedido")
        
        # TODO: Send push notification based on status
        
        return updated_order
    
    async def accept_order(
        self,
        order_id: str,
        estimated_minutes: int,
        user_id: str
    ) -> Order:
        """Accept an order (business action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        # Verify user is branch manager or business owner
        branch = await branches_repo.get_by_id(order.branchId)
        business = await businesses_repo.get_by_id(order.businessId)
        
        if business.ownerId != user_id and user_id not in branch.managerIds:
            raise ValueError("No autorizado para aceptar este pedido")
        
        return await self.update_status(
            order_id,
            OrderStatus.ACCEPTED,
            OrderActor.BUSINESS,
            f"Pedido aceptado. Tiempo estimado: {estimated_minutes} minutos"
        )
    
    async def reject_order(
        self,
        order_id: str,
        reason: str,
        user_id: str
    ) -> Order:
        """Reject an order (business action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        branch = await branches_repo.get_by_id(order.branchId)
        business = await businesses_repo.get_by_id(order.businessId)
        
        if business.ownerId != user_id and user_id not in branch.managerIds:
            raise ValueError("No autorizado para rechazar este pedido")
        
        # TODO: Process refund if payment was made
        
        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.BUSINESS,
            f"Pedido rechazado: {reason}"
        )

    async def modify_order_items(
        self,
        order_id: str,
        new_items: List[dict],
        reason: str,
        user_id: str
    ) -> Order:
        """Modify order items (business action for out of stock, etc.)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.status not in [OrderStatus.PENDING_ACCEPTANCE, OrderStatus.ACCEPTED]:
            raise ValueError("No se puede modificar el pedido en este estado")
        
        branch = await branches_repo.get_by_id(order.branchId)
        business = await businesses_repo.get_by_id(order.businessId)
        
        if business.ownerId != user_id and user_id not in branch.managerIds:
            raise ValueError("No autorizado para modificar este pedido")
        
        # Build new items list with snapshots
        modified_items: List[OrderItem] = []
        subtotal = 0.0
        
        for item in new_items:
            product = await products_repo.get_by_id(item["productId"])
            if not product:
                raise ValueError(f"Producto {item['productId']} no encontrado")
            
            # Check if this item was modified
            original_item = next(
                (i for i in order.items if i.productId == item["productId"]),
                None
            )
            was_modified = (
                original_item is None or
                original_item.quantity != item["quantity"] or
                original_item.price != product.price
            )
            
            order_item = OrderItem(
                productId=product.id,
                name=product.name,
                price=product.price,
                quantity=item["quantity"],
                imageUrl=product.image,
                wasModifiedByStore=was_modified
            )
            modified_items.append(order_item)
            subtotal += product.price * item["quantity"]
        
        # Recalculate total
        total_discounts = sum(d.amount for d in order.discounts)
        total = round(subtotal + order.deliveryFee - total_discounts, 2)
        
        timeline_entry = OrderTimeline(
            status=OrderStatus.MODIFIED_BY_STORE,
            timestamp=datetime.utcnow(),
            message=f"Pedido modificado: {reason}",
            actor=OrderActor.BUSINESS
        )
        
        updated_order = await self.orders_repo.update_items(
            order_id, modified_items, round(subtotal, 2), total, timeline_entry
        )
        
        if not updated_order:
            raise ValueError("Error al modificar el pedido")
        
        # TODO: Send push notification to customer
        
        return updated_order
    
    async def accept_modifications(self, order_id: str, user_id: str) -> Order:
        """Accept store modifications (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.customerId != user_id:
            raise ValueError("No autorizado")
        
        if order.status != OrderStatus.MODIFIED_BY_STORE:
            raise ValueError("El pedido no tiene modificaciones pendientes")
        
        return await self.update_status(
            order_id,
            OrderStatus.ACCEPTED,
            OrderActor.CUSTOMER,
            "Cliente aceptó las modificaciones"
        )
    
    async def reject_modifications(self, order_id: str, user_id: str) -> Order:
        """Reject store modifications and cancel order (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.customerId != user_id:
            raise ValueError("No autorizado")
        
        if order.status != OrderStatus.MODIFIED_BY_STORE:
            raise ValueError("El pedido no tiene modificaciones pendientes")
        
        # TODO: Process refund
        
        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.CUSTOMER,
            "Cliente rechazó las modificaciones"
        )

    async def cancel_order(
        self,
        order_id: str,
        user_id: str,
        reason: Optional[str] = None
    ) -> Order:
        """Cancel an order (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.customerId != user_id:
            raise ValueError("No autorizado")
        
        # Can only cancel in early stages
        cancellable_statuses = [
            OrderStatus.PENDING_ACCEPTANCE,
            OrderStatus.MODIFIED_BY_STORE,
            OrderStatus.ACCEPTED
        ]
        if order.status not in cancellable_statuses:
            raise ValueError("No se puede cancelar el pedido en este estado")
        
        # TODO: Process refund based on status
        
        message = "Pedido cancelado por el cliente"
        if reason:
            message += f": {reason}"
        
        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.CUSTOMER,
            message
        )
    
    async def accept_delivery(self, order_id: str, user_id: str) -> Order:
        """Accept order for delivery (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.status != OrderStatus.READY_FOR_PICKUP:
            raise ValueError("El pedido no está listo para recoger")
        
        if order.deliveryPersonId:
            raise ValueError("El pedido ya tiene un repartidor asignado")
        
        # Get delivery person
        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise ValueError("No eres un repartidor registrado")
        
        if delivery_person.currentOrderId:
            raise ValueError("Ya tienes un pedido en curso")
        
        # Assign delivery person
        estimated_time = datetime.utcnow() + timedelta(minutes=30)
        await self.orders_repo.assign_delivery_person(
            order_id, delivery_person.id, estimated_time
        )
        await self.delivery_repo.assign_order(delivery_person.id, order_id)
        
        return await self.update_status(
            order_id,
            OrderStatus.READY_FOR_PICKUP,
            OrderActor.DELIVERY,
            f"Repartidor {delivery_person.name} asignado"
        )
    
    async def confirm_pickup(self, order_id: str, user_id: str) -> Order:
        """Confirm order pickup from store (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or delivery_person.id != order.deliveryPersonId:
            raise ValueError("No autorizado")
        
        return await self.update_status(
            order_id,
            OrderStatus.ON_THE_WAY,
            OrderActor.DELIVERY,
            "Pedido recogido, en camino"
        )
    
    async def confirm_delivery(self, order_id: str, user_id: str) -> Order:
        """Confirm order delivery (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or delivery_person.id != order.deliveryPersonId:
            raise ValueError("No autorizado")
        
        # Complete delivery
        await self.delivery_repo.complete_delivery(delivery_person.id)
        
        # Update payment status if cash
        if order.paymentMethod == "cash":
            await self.orders_repo.update_payment_status(
                order_id, PaymentStatus.COMPLETED
            )
        
        return await self.update_status(
            order_id,
            OrderStatus.DELIVERED,
            OrderActor.DELIVERY,
            "Pedido entregado"
        )

    async def add_comment(
        self,
        order_id: str,
        user_id: str,
        message: str
    ) -> Order:
        """Add a comment to an order."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        # Determine actor
        if order.customerId == user_id:
            actor = OrderActor.CUSTOMER
        else:
            branch = await branches_repo.get_by_id(order.branchId)
            business = await businesses_repo.get_by_id(order.businessId)
            if business.ownerId == user_id or user_id in branch.managerIds:
                actor = OrderActor.BUSINESS
            else:
                raise ValueError("No autorizado para comentar en este pedido")
        
        comment = OrderComment(
            id=str(uuid.uuid4()),
            author=actor,
            message=message,
            timestamp=datetime.utcnow()
        )
        
        updated_order = await self.orders_repo.add_comment(order_id, comment)
        if not updated_order:
            raise ValueError("Error al agregar comentario")
        
        return updated_order
    
    async def rate_order(
        self,
        order_id: str,
        user_id: str,
        rating: int,
        comment: Optional[str] = None
    ) -> Order:
        """Rate a delivered order."""
        if rating < 1 or rating > 5:
            raise ValueError("La calificación debe ser entre 1 y 5")
        
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        if order.customerId != user_id:
            raise ValueError("No autorizado")
        
        if order.status != OrderStatus.DELIVERED:
            raise ValueError("Solo se pueden calificar pedidos entregados")
        
        if order.rating:
            raise ValueError("El pedido ya fue calificado")
        
        # Update order rating
        updated_order = await self.orders_repo.add_rating(order_id, rating, comment)
        
        # Update delivery person rating if applicable
        if order.deliveryPersonId:
            await self.delivery_repo.update_rating(order.deliveryPersonId, rating)
        
        return updated_order
    
    async def get_order_tracking(
        self,
        order_id: str,
        user_id: str
    ) -> dict:
        """Get order tracking information."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        
        # Verify access
        if order.customerId != user_id:
            branch = await branches_repo.get_by_id(order.branchId)
            business = await businesses_repo.get_by_id(order.businessId)
            delivery_person = None
            if order.deliveryPersonId:
                delivery_person = await self.delivery_repo.get_by_id(order.deliveryPersonId)
            
            is_authorized = (
                business.ownerId == user_id or
                user_id in branch.managerIds or
                (delivery_person and delivery_person.userId == user_id)
            )
            if not is_authorized:
                raise ValueError("No autorizado")
        
        # Get branch location
        branch = await branches_repo.get_by_id(order.branchId)
        store_location = {
            "longitude": branch.coordinates.coordinates[0],
            "latitude": branch.coordinates.coordinates[1]
        }
        
        # Get delivery location
        delivery_location = {
            "longitude": order.deliveryAddress.coordinates.coordinates[0],
            "latitude": order.deliveryAddress.coordinates.coordinates[1]
        }
        
        # Get delivery person location if assigned
        delivery_person_location = None
        if order.deliveryPersonId:
            delivery_person = await self.delivery_repo.get_by_id(order.deliveryPersonId)
            if delivery_person and delivery_person.currentLocation:
                delivery_person_location = {
                    "longitude": delivery_person.currentLocation.coordinates[0],
                    "latitude": delivery_person.currentLocation.coordinates[1]
                }
        
        # Calculate distance and ETA
        distance_km = None
        estimated_minutes = None
        if delivery_person_location:
            distance_km = haversine_distance(
                (delivery_person_location["longitude"], delivery_person_location["latitude"]),
                (delivery_location["longitude"], delivery_location["latitude"])
            )
            # Estimate 25 km/h average speed
            estimated_minutes = int((distance_km / 25) * 60)
        
        return {
            "order": order,
            "storeLocation": store_location,
            "deliveryLocation": delivery_location,
            "deliveryPersonLocation": delivery_person_location,
            "distanceKm": round(distance_km, 2) if distance_km else None,
            "estimatedMinutes": estimated_minutes
        }
