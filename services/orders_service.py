"""Order service with business logic."""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from domain.orders import (
    ALLOWED_TRANSITIONS,
    AddressType,
    DeliveryAddress,
    GeoPoint,
    Order,
    OrderActor,
    OrderComment,
    OrderDiscount,
    OrderItem,
    OrderStatus,
    OrderTimeline,
    PaymentStatus,
    PickupAddress,
)
from repositories import (
    branches_repo,
    businesses_repo,
    combos_repo,
    payment_methods_repo,
    products_repo,
    showcases_repo,
)
from repositories.orders_repository import (
    DeliveryPersonRepository,
    OrderLocationRepository,
    OrderRepository,
)
from services.access_checker import access_checker
from services.orders_utils import (
    calculate_delivery_fee_h3,
    coords_to_h3,
    generate_order_number,
    haversine_distance,
)


class OrderService:
    """Service for order business logic."""

    def __init__(self):
        self.orders_repo = OrderRepository()
        self.delivery_repo = DeliveryPersonRepository()
        self.locations_repo = OrderLocationRepository()

    @staticmethod
    def _ids_equal(a, b) -> bool:
        return str(a) == str(b)

    @staticmethod
    def _normalize_currency(currency: Optional[str], fallback: str = "USD") -> str:
        normalized = (currency or "").strip().upper()
        if normalized in {"USD", "CUP"}:
            return normalized
        return fallback.upper()

    @staticmethod
    def _resolve_exchange_rate(branch: Any) -> Optional[float]:
        rate = getattr(branch, "exchangeRate", None)
        if rate is None:
            return None
        try:
            value = float(rate)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    def _convert_amount(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        exchange_rate: Optional[float],
    ) -> float:
        value = float(amount or 0.0)
        from_curr = self._normalize_currency(from_currency, fallback="USD")
        to_curr = self._normalize_currency(to_currency, fallback="USD")

        if from_curr == to_curr:
            return value

        if not exchange_rate or exchange_rate <= 0:
            raise ValueError(
                "Falta exchangeRate vÃ¡lido en la sucursal para convertir monedas"
            )

        if from_curr == "USD" and to_curr == "CUP":
            return value * exchange_rate
        if from_curr == "CUP" and to_curr == "USD":
            return value / exchange_rate
        raise ValueError(
            f"ConversiÃ³n de moneda no soportada: {from_curr} -> {to_curr}"
        )

    async def _resolve_payment_method(
        self, payment_method: str
    ) -> tuple[str, Optional[str], Optional[Any]]:
        payment_method_raw = str(payment_method or "").strip()
        if not payment_method_raw:
            raise ValueError("paymentMethod es requerido")

        payment_method_doc = None
        if len(payment_method_raw) == 24:
            payment_method_doc = await payment_methods_repo.get_by_id(
                payment_method_raw
            )
        if not payment_method_doc:
            payment_method_doc = await payment_methods_repo.get_by_code(
                payment_method_raw
            )

        if payment_method_doc:
            return (
                payment_method_doc.code,
                self._normalize_currency(payment_method_doc.currency, fallback="USD"),
                payment_method_doc,
            )

        # Legacy fallback: accept plain code even if not found in DB.
        return payment_method_raw, None, None

    def _resolve_order_currency(
        self, branch: Any, payment_method_currency: Optional[str]
    ) -> str:
        if payment_method_currency in {"USD", "CUP"}:
            return payment_method_currency

        accepted_currency = (getattr(branch, "acceptedCurrency", None) or "").upper()
        if accepted_currency in {"USD", "CUP"}:
            return accepted_currency
        if accepted_currency == "BOTH":
            return "USD"
        return "USD"

    async def _build_combo_selection_snapshot(
        self,
        combo: Any,
        combo_selections: List[dict],
        branch_id: str,
        order_currency: str,
        exchange_rate: Optional[float],
    ) -> tuple[list[Any], list[Any], bool, float, float, str, float]:
        """Build validated combo selection snapshot and prices for one combo unit."""
        selection_map: Dict[str, dict] = {}
        for slot_selection in combo_selections or []:
            slot_id = str(slot_selection.get("slotId") or "").strip()
            if not slot_id:
                raise ValueError("Cada selección de combo debe incluir slotId")
            if slot_id in selection_map:
                raise ValueError(f"Slot duplicado en selección de combo: {slot_id}")
            selection_map[slot_id] = slot_selection

        combo_slots = list(combo.slots or [])
        combo_slot_ids = {str(slot.id) for slot in combo_slots}
        unknown_slots = set(selection_map.keys()) - combo_slot_ids
        if unknown_slots:
            raise ValueError(
                f"Hay slots inválidos en la selección del combo: {sorted(unknown_slots)}"
            )

        combo_currency = self._normalize_currency(
            getattr(combo, "currency", None), fallback=order_currency
        )
        product_cache: Dict[str, Any] = {}
        selection_snapshots = []
        preview_products = []
        preview_product_ids = set()
        base_unit_total = 0.0

        def add_preview_product(product: Any) -> None:
            product_id = str(product.id)
            if product_id in preview_product_ids or len(preview_products) >= 4:
                return
            preview_product_ids.add(product_id)
            preview_products.append(
                {
                    "productId": product_id,
                    "name": product.name,
                    "imageUrl": getattr(product, "image", None),
                }
            )

        for slot in combo_slots:
            slot_id = str(slot.id)
            slot_is_free = bool(getattr(slot, "isFree", False))
            provided_selection = selection_map.get(slot_id)

            if provided_selection:
                selected_options_input = provided_selection.get("selectedOptions") or []
            else:
                selected_options_input = []
                if slot.minSelections > 0:
                    defaults = [opt for opt in slot.options if opt.isDefault]
                    if not defaults:
                        defaults = list(slot.options)
                    if not defaults:
                        raise ValueError(f"El slot '{slot.name}' no tiene opciones")

                    required_count = max(int(slot.minSelections or 0), 1)
                    for idx in range(required_count):
                        default_option = defaults[idx % len(defaults)]
                        selected_options_input.append(
                            {
                                "productId": str(default_option.productId),
                                "quantity": 1,
                                "modifiers": [],
                            }
                        )

            selected_count = 0
            selected_option_snapshots = []
            options_by_product_id = {
                str(option.productId): option for option in (slot.options or [])
            }

            for selected in selected_options_input:
                selected_product_id = str(selected.get("productId") or "").strip()
                if not selected_product_id:
                    raise ValueError(
                        f"Cada opción seleccionada del slot '{slot.name}' debe incluir productId"
                    )

                selected_quantity = int(selected.get("quantity") or 0)
                if selected_quantity <= 0:
                    raise ValueError(
                        f"La cantidad seleccionada en slot '{slot.name}' debe ser mayor que 0"
                    )

                selected_count += selected_quantity
                combo_option = options_by_product_id.get(selected_product_id)
                if not combo_option:
                    raise ValueError(
                        f"El producto {selected_product_id} no pertenece al slot '{slot.name}'"
                    )

                product = product_cache.get(selected_product_id)
                if not product:
                    product = await products_repo.get_by_id(selected_product_id)
                    if not product:
                        raise ValueError(
                            f"Producto {selected_product_id} no encontrado"
                        )
                    product_cache[selected_product_id] = product

                if not product.availability:
                    raise ValueError(f"Producto {product.name} no disponible")
                if not self._ids_equal(product.branchId, branch_id):
                    raise ValueError(
                        f"Producto {product.name} no pertenece a esta sucursal"
                    )
                add_preview_product(product)

                if slot_is_free:
                    product_price = 0.0
                    option_adjustment = 0.0
                else:
                    product_price = self._convert_amount(
                        amount=product.price,
                        from_currency=self._normalize_currency(
                            getattr(product, "currency", None), fallback=order_currency
                        ),
                        to_currency=order_currency,
                        exchange_rate=exchange_rate,
                    )
                    option_adjustment = self._convert_amount(
                        amount=combo_option.priceAdjustment,
                        from_currency=combo_currency,
                        to_currency=order_currency,
                        exchange_rate=exchange_rate,
                    )

                modifiers_input = selected.get("modifiers") or []
                available_modifiers = {
                    (modifier.name or "").strip().lower(): modifier
                    for modifier in (combo_option.availableModifiers or [])
                    if (modifier.name or "").strip()
                }
                modifier_snapshots = []
                modifiers_total = 0.0
                for mod in modifiers_input:
                    mod_name = str(mod.get("name") or "").strip()
                    if not mod_name:
                        raise ValueError(
                            f"Modifier inválido en el slot '{slot.name}' del combo"
                        )
                    matched_modifier = available_modifiers.get(mod_name.lower())
                    if not matched_modifier:
                        raise ValueError(
                            f"Modifier '{mod_name}' no permitido para '{product.name}'"
                        )

                    if slot_is_free:
                        mod_adjustment = 0.0
                    else:
                        mod_adjustment = self._convert_amount(
                            amount=matched_modifier.priceAdjustment,
                            from_currency=combo_currency,
                            to_currency=order_currency,
                            exchange_rate=exchange_rate,
                        )
                    modifiers_total += mod_adjustment
                    modifier_snapshots.append(
                        {
                            "name": matched_modifier.name,
                            "priceAdjustment": round(mod_adjustment, 2),
                        }
                    )

                base_option_total = (
                    product_price + option_adjustment + modifiers_total
                ) * selected_quantity
                base_unit_total += base_option_total

                selected_option_snapshots.append(
                    {
                        "productId": str(product.id),
                        "name": product.name,
                        "price": round(product_price, 2),
                        "quantity": selected_quantity,
                        "priceAdjustment": round(option_adjustment, 2),
                        "modifiers": modifier_snapshots,
                    }
                )

            if selected_count < int(slot.minSelections or 0):
                raise ValueError(
                    f"El slot '{slot.name}' requiere al menos {slot.minSelections} selección(es)"
                )
            if selected_count > int(slot.maxSelections or 0):
                raise ValueError(
                    f"El slot '{slot.name}' permite máximo {slot.maxSelections} selección(es)"
                )

            if selected_option_snapshots:
                selection_snapshots.append(
                    {
                        "slotId": slot_id,
                        "slotName": slot.name,
                        "selectedOptions": selected_option_snapshots,
                    }
                )

        has_gift = bool(getattr(combo, "giftOptions", []))

        if not preview_products:
            for slot in combo_slots:
                default_option = next(
                    (opt for opt in slot.options if opt.isDefault),
                    slot.options[0] if slot.options else None,
                )
                if not default_option:
                    continue

                default_product_id = str(default_option.productId)
                product = product_cache.get(default_product_id)
                if not product:
                    product = await products_repo.get_by_id(default_product_id)
                    if not product:
                        continue
                    product_cache[default_product_id] = product
                add_preview_product(product)
                if len(preview_products) >= 4:
                    break

        discount_type = str(getattr(combo, "discountType", "none") or "none").lower()
        discount_value_raw = float(getattr(combo, "discountValue", 0.0) or 0.0)
        discount_value_snapshot = discount_value_raw
        discount_amount = 0.0

        if discount_type == "percentage":
            if discount_value_raw < 0 or discount_value_raw > 100:
                raise ValueError(
                    f"El combo '{combo.name}' tiene descuento porcentual inválido"
                )
            discount_amount = base_unit_total * (discount_value_raw / 100)
        elif discount_type == "fixed":
            if discount_value_raw < 0:
                raise ValueError(
                    f"El combo '{combo.name}' tiene descuento fijo inválido"
                )
            discount_value_snapshot = self._convert_amount(
                amount=discount_value_raw,
                from_currency=combo_currency,
                to_currency=order_currency,
                exchange_rate=exchange_rate,
            )
            discount_amount = discount_value_snapshot
            discount_value_snapshot = round(discount_value_snapshot, 2)
        else:
            discount_type = "none"
            discount_value_snapshot = 0.0

        final_unit_total = max(0.0, base_unit_total - discount_amount)
        return (
            selection_snapshots,
            preview_products,
            has_gift,
            round(base_unit_total, 2),
            round(final_unit_total, 2),
            discount_type,
            discount_value_snapshot,
        )

    async def _build_order_item_snapshot(
        self,
        item: dict,
        branch_id: str,
        order_currency: str,
        exchange_rate: Optional[float],
    ) -> tuple[OrderItem, float]:
        """Build order item snapshot and line subtotal from raw input."""
        item_type = str(item.get("itemType") or "product").strip().lower()
        quantity = int(item.get("quantity") or 0)
        if quantity <= 0:
            raise ValueError("La cantidad de cada ítem debe ser mayor que 0")

        if item_type == "product":
            product_id = item.get("itemId") or item.get("productId")
            if not product_id:
                raise ValueError("productId es requerido para ítems de tipo product")

            product = await products_repo.get_by_id(product_id)
            if not product:
                raise ValueError(f"Producto {product_id} no encontrado")
            if not product.availability:
                raise ValueError(f"Producto {product.name} no disponible")
            if not self._ids_equal(product.branchId, branch_id):
                raise ValueError(
                    f"Producto {product.name} no pertenece a esta sucursal"
                )

            unit_price = self._convert_amount(
                amount=product.price,
                from_currency=self._normalize_currency(
                    getattr(product, "currency", None), fallback=order_currency
                ),
                to_currency=order_currency,
                exchange_rate=exchange_rate,
            )
            unit_price = round(unit_price, 2)
            order_item = OrderItem(
                itemId=str(product.id),
                itemType="product",
                name=product.name,
                basePrice=unit_price,
                finalPrice=unit_price,
                quantity=quantity,
                imageUrl=product.image,
                wasModifiedByStore=False,
            )
            return order_item, round(unit_price * quantity, 2)

        if item_type == "combo":
            combo_id = item.get("itemId") or item.get("comboId")
            if not combo_id:
                raise ValueError("comboId es requerido para ítems de tipo combo")

            combo = await combos_repo.get_by_id(combo_id)
            if not combo:
                raise ValueError(f"Combo {combo_id} no encontrado")
            if not combo.availability:
                raise ValueError(f"Combo {combo.name} no disponible")
            if not self._ids_equal(combo.branchId, branch_id):
                raise ValueError(f"El combo {combo.name} no pertenece a esta sucursal")

            combo_selections_input = item.get("comboSelections") or []
            (
                combo_selection_snapshots,
                preview_products,
                has_gift,
                base_unit_price,
                final_unit_price,
                discount_type,
                discount_value,
            ) = await self._build_combo_selection_snapshot(
                combo=combo,
                combo_selections=combo_selections_input,
                branch_id=branch_id,
                order_currency=order_currency,
                exchange_rate=exchange_rate,
            )

            image_path = combo.image
            if not image_path and preview_products:
                image_path = preview_products[0].get("imageUrl")

            order_item = OrderItem(
                itemId=str(combo.id),
                itemType="combo",
                name=combo.name,
                basePrice=base_unit_price,
                finalPrice=final_unit_price,
                quantity=quantity,
                imageUrl=image_path,
                wasModifiedByStore=False,
                comboSelections=combo_selection_snapshots,
                hasGift=has_gift,
                discountType=discount_type,
                discountValue=float(discount_value),
                previewProducts=preview_products,
            )
            return order_item, round(final_unit_price * quantity, 2)

        if item_type == "showcase":
            showcase_id = item.get("itemId") or item.get("showcaseId")
            if not showcase_id:
                raise ValueError("showcaseId es requerido para ítems de tipo showcase")

            request_description = (item.get("description") or "").strip()
            if not request_description:
                raise ValueError(
                    "Para ítems de vitrina debes escribir una descripción de lo que deseas"
                )

            showcase = await showcases_repo.get_by_id(showcase_id)
            if not showcase:
                raise ValueError(f"Vitrina {showcase_id} no encontrada")
            if not showcase.isActive:
                raise ValueError(f"La vitrina {showcase.title} no está disponible")
            if not self._ids_equal(showcase.branchId, branch_id):
                raise ValueError("La vitrina no pertenece a esta sucursal")

            order_item = OrderItem(
                itemId=str(showcase.id),
                itemType="showcase",
                name=f"Pedido de vitrina: {showcase.title}",
                basePrice=0.0,
                finalPrice=0.0,
                quantity=quantity,
                imageUrl=showcase.image,
                requestDescription=request_description,
                wasModifiedByStore=False,
            )
            return order_item, 0.0

        raise ValueError(f"Tipo de ítem no soportado: {item_type}")

    async def create_order(
        self,
        customer_id: str,
        branch_id: str,
        items: List[dict],
        delivery_address: dict,
        payment_method: str,
        payment_intent_id: Optional[str] = None,
        promo_code: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> Order:
        """Create a new order with all validations."""
        # 1. Validate branch exists and is active
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise ValueError("Sucursal no encontrada")
        if not branch.isActive:
            raise ValueError("La sucursal no está activa")
        if not items:
            raise ValueError("El pedido debe incluir al menos un ítem")

        # 1.5. Resolve payment method and monetary context
        (
            payment_method_code,
            payment_method_currency,
            _payment_method_doc,
        ) = await self._resolve_payment_method(payment_method)
        order_currency = self._resolve_order_currency(branch, payment_method_currency)
        exchange_rate = self._resolve_exchange_rate(branch)

        # 2. Get business
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            raise ValueError("Negocio no encontrado")

        # 3. Validate and snapshot items in order currency
        order_items: List[OrderItem] = []
        subtotal = 0.0

        for item in items:
            order_item, line_subtotal = await self._build_order_item_snapshot(
                item=item,
                branch_id=branch_id,
                order_currency=order_currency,
                exchange_rate=exchange_rate,
            )
            order_items.append(order_item)
            subtotal += line_subtotal

        subtotal = round(subtotal, 2)

        # 4. Calculate delivery fee using H3 zones (zone config in CUP)
        branch_coords = (
            branch.coordinates.coordinates[0],
            branch.coordinates.coordinates[1],
        )
        delivery_coords = (delivery_address["longitude"], delivery_address["latitude"])

        subtotal_for_zone = subtotal
        if order_currency != "CUP":
            subtotal_for_zone = self._convert_amount(
                amount=subtotal,
                from_currency=order_currency,
                to_currency="CUP",
                exchange_rate=exchange_rate,
            )

        delivery_fee_cup, delivery_zone_id = await calculate_delivery_fee_h3(
            branch_coords,
            delivery_coords,
            subtotal_for_zone,
        )

        if order_currency == "CUP":
            delivery_fee = delivery_fee_cup
        else:
            delivery_fee = self._convert_amount(
                amount=delivery_fee_cup,
                from_currency="CUP",
                to_currency=order_currency,
                exchange_rate=exchange_rate,
            )

        delivery_fee = round(delivery_fee, 2)
        delivery_mode = "app"

        # H3 index of branch for efficient geo queries by delivery persons
        branch_h3 = coords_to_h3(branch_coords[1], branch_coords[0])

        # 5. Apply discounts
        discounts: List[OrderDiscount] = []

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
        if payment_method_code in {"card", "stripe"}:
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
                coordinates=[
                    delivery_address["longitude"],
                    delivery_address["latitude"],
                ],
            ),
            # Delivery instruction fields (Uber Eats / Glovo style)
            addressType=AddressType(delivery_address.get("addressType", "house")),
            buildingName=delivery_address.get("buildingName"),
            floor=delivery_address.get("floor"),
            apartment=delivery_address.get("apartment"),
            deliveryInstructions=delivery_address.get("deliveryInstructions"),
        )

        pickup_addr = PickupAddress(
            street=branch.address,
            coordinates=GeoPoint(
                type="Point",
                coordinates=list(branch.coordinates.coordinates),
            ),
        )

        timeline = [
            OrderTimeline(
                status=OrderStatus.PENDING_ACCEPTANCE,
                timestamp=now,
                message="Pedido creado, esperando confirmación de la tienda",
                actor=OrderActor.SYSTEM,
            )
        ]

        comments = []
        if initial_comment:
            comments.append(
                OrderComment(
                    id=str(uuid.uuid4()),
                    author=OrderActor.CUSTOMER,
                    message=initial_comment,
                    timestamp=now,
                )
            )

        order = Order(
            _id=order_id,
            orderNumber=order_number,
            customerId=customer_id,
            branchId=branch_id,
            businessId=business.id,
            items=order_items,
            subtotal=subtotal,
            deliveryFee=delivery_fee,
            deliveryMode=delivery_mode,
            deliveryZoneId=delivery_zone_id,
            branchH3=branch_h3,
            discounts=discounts,
            total=total,
            currency=order_currency,
            status=OrderStatus.PENDING_ACCEPTANCE,
            deliveryAddress=delivery_addr,
            pickupAddress=pickup_addr,
            timeline=timeline,
            comments=comments,
            paymentMethod=payment_method_code,
            paymentStatus=payment_status,
            paymentId=payment_intent_id,
            createdAt=now,
            updatedAt=now,
            lastStatusAt=now,
        )

        created_order = await self.orders_repo.create(order)

        # 8. Send push notification to branch managers/owner
        await self._send_new_order_notification_to_business(
            created_order, branch, business
        )

        return created_order

    def _validate_transition(
        self, current_status: OrderStatus, new_status: OrderStatus
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
        force: bool = False,
    ) -> Order:
        """Update order status with validation."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not force and not self._validate_transition(order.status, new_status):
            raise ValueError(
                f"TransiciÃ³n de estado no permitida: {order.status.value} -> {new_status.value}"
            )

        # VALIDACIÃ“N CRÃTICA: Verificar pago antes de PREPARING
        if new_status == OrderStatus.PREPARING:
            payment_method = order.paymentMethod.lower()

            # Efectivo no requiere pago previo (se paga al entregar)
            if payment_method not in ["cash", "efectivo"]:
                if order.paymentStatus != PaymentStatus.COMPLETED:
                    raise ValueError(
                        "El pedido debe estar pagado antes de prepararse. "
                        "El cliente debe completar el pago primero."
                    )

        # Default messages
        if not message:
            messages = {
                OrderStatus.AWAITING_DELIVERY_ACCEPTANCE: "Pedido aceptado por tienda, esperando mensajero",
                OrderStatus.ACCEPTED: "Pedido aceptado por la tienda",
                OrderStatus.PENDING_PAYMENT: "Mensajero confirmado. Pedido listo para pagar",
                OrderStatus.PREPARING: "Tu pedido estÃ¡ siendo preparado",
                OrderStatus.READY_FOR_PICKUP: "Pedido listo para recoger",
                OrderStatus.ON_THE_WAY: "Tu pedido estÃ¡ en camino",
                OrderStatus.DELIVERED: "Pedido entregado",
                OrderStatus.CANCELLED: "Pedido cancelado",
                OrderStatus.MODIFIED_BY_STORE: "La tienda ha modificado tu pedido",
            }
            message = messages.get(
                new_status, f"Estado actualizado a {new_status.value}"
            )

        timeline_entry = OrderTimeline(
            status=new_status, timestamp=datetime.utcnow(), message=message, actor=actor
        )

        updated_order = await self.orders_repo.update_status(
            order_id, new_status, timeline_entry
        )

        if not updated_order:
            raise ValueError("Error al actualizar el pedido")

        # TODO: Send push notification based on status

        # Emit tracking event for real-time subscription
        await self._emit_tracking_event(updated_order)

        return updated_order

    async def accept_order(
        self,
        order_id: str,
        estimated_minutes: int,
        user_id: str,
        delivery_fee_override: Optional[float] = None,
    ) -> Order:
        """Accept an order (business action).

        Args:
            order_id: The order ID to accept.
            estimated_minutes: Estimated delivery time in minutes.
            user_id: The user performing the action.
            delivery_fee_override: Optional delivery fee set manually by the branch.
                When provided, the order's deliveryMode is set to "branch" and
                the total is recalculated with the new fee.
        """
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify user has access to the branch
        has_access, error_msg = await access_checker.check_branch_access(
            user_id, order.branchId
        )
        if not has_access:
            raise ValueError(error_msg or "No autorizado para aceptar este pedido")

        # If branch sets its own delivery fee, update it before accepting
        if delivery_fee_override is not None:
            if delivery_fee_override < 0:
                raise ValueError("El precio de envÃ­o no puede ser negativo")
            total_discounts = sum(d.amount for d in order.discounts)
            new_total = round(
                order.subtotal + delivery_fee_override - total_discounts, 2
            )
            await self.orders_repo.update_delivery_fee(
                order_id, delivery_fee_override, new_total, delivery_mode="branch"
            )

        return await self.update_status(
            order_id,
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            OrderActor.BUSINESS,
            f"Pedido aceptado por tienda. Esperando mensajero. Tiempo estimado: {estimated_minutes} minutos",
        )

    async def reject_order(self, order_id: str, reason: str, user_id: str) -> Order:
        """Reject an order (business action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify user has access to the branch
        has_access, error_msg = await access_checker.check_branch_access(
            user_id, order.branchId
        )
        if not has_access:
            raise ValueError(error_msg or "No autorizado para rechazar este pedido")

        # TODO: Process refund if payment was made

        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.BUSINESS,
            f"Pedido rechazado: {reason}",
        )

    async def modify_order_items(
        self, order_id: str, new_items: List[dict], reason: str, user_id: str
    ) -> Order:
        """Modify order items (business action for out of stock, etc.)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status not in [
            OrderStatus.PENDING_ACCEPTANCE,
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.ACCEPTED,
        ]:
            raise ValueError("No se puede modificar el pedido en este estado")

        # Verify user has access to the branch
        has_access, error_msg = await access_checker.check_branch_access(
            user_id, order.branchId
        )
        if not has_access:
            raise ValueError(error_msg or "No autorizado para modificar este pedido")

        branch = await branches_repo.get_by_id(order.branchId)
        if not branch:
            raise ValueError("Sucursal no encontrada")
        exchange_rate = self._resolve_exchange_rate(branch)
        order_currency = self._normalize_currency(order.currency, fallback="USD")

        # Build new items list with snapshots
        modified_items: List[OrderItem] = []
        subtotal = 0.0

        for item in new_items:
            order_item, line_subtotal = await self._build_order_item_snapshot(
                item=item,
                branch_id=str(order.branchId),
                order_currency=order_currency,
                exchange_rate=exchange_rate,
            )

            # Check if this item was modified
            original_item = next(
                (
                    i
                    for i in order.items
                    if i.itemType == order_item.itemType
                    and self._ids_equal(i.itemId, order_item.itemId)
                    and (i.requestDescription or "")
                    == (order_item.requestDescription or "")
                ),
                None,
            )
            was_modified = (
                original_item is None
                or original_item.quantity != order_item.quantity
                or original_item.finalPrice != order_item.finalPrice
                or original_item.name != order_item.name
                or (original_item.comboSelections or [])
                != (order_item.comboSelections or [])
                or bool(getattr(original_item, "hasGift", False))
                != bool(order_item.hasGift)
            )

            order_item.wasModifiedByStore = was_modified
            modified_items.append(order_item)
            subtotal += line_subtotal

        # Recalculate total
        total_discounts = sum(d.amount for d in order.discounts)
        total = round(subtotal + order.deliveryFee - total_discounts, 2)

        timeline_entry = OrderTimeline(
            status=OrderStatus.MODIFIED_BY_STORE,
            timestamp=datetime.utcnow(),
            message=f"Pedido modificado: {reason}",
            actor=OrderActor.BUSINESS,
        )

        updated_order = await self.orders_repo.update_items(
            order_id, modified_items, round(subtotal, 2), total, timeline_entry
        )

        if not updated_order:
            raise ValueError("Error al modificar el pedido")

        # TODO: Send push notification to customer

        # Emit tracking event for real-time subscription
        await self._emit_tracking_event(updated_order)

        return updated_order

    async def accept_modifications(self, order_id: str, user_id: str) -> Order:
        """Accept store modifications (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        if order.status != OrderStatus.MODIFIED_BY_STORE:
            raise ValueError("El pedido no tiene modificaciones pendientes")

        next_status = (
            OrderStatus.ACCEPTED
            if order.paymentStatus == PaymentStatus.COMPLETED
            else OrderStatus.AWAITING_DELIVERY_ACCEPTANCE
        )

        return await self.update_status(
            order_id,
            next_status,
            OrderActor.CUSTOMER,
            "Cliente aceptÃ³ las modificaciones",
        )

    async def reject_modifications(self, order_id: str, user_id: str) -> Order:
        """Reject store modifications and cancel order (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        if order.status != OrderStatus.MODIFIED_BY_STORE:
            raise ValueError("El pedido no tiene modificaciones pendientes")

        # TODO: Process refund

        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.CUSTOMER,
            "Cliente rechazÃ³ las modificaciones",
        )

    async def cancel_order(
        self, order_id: str, user_id: str, reason: Optional[str] = None
    ) -> Order:
        """Cancel an order (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        # Can only cancel in early stages
        cancellable_statuses = [
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PENDING_ACCEPTANCE,
            OrderStatus.MODIFIED_BY_STORE,
            OrderStatus.ACCEPTED,
        ]
        if order.status not in cancellable_statuses:
            raise ValueError("No se puede cancelar el pedido en este estado")

        # TODO: Process refund based on status

        message = "Pedido cancelado por el cliente"
        if reason:
            message += f": {reason}"

        return await self.update_status(
            order_id, OrderStatus.CANCELLED, OrderActor.CUSTOMER, message
        )

    async def accept_delivery(self, order_id: str, user_id: str) -> Order:
        """Accept order for delivery (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status != OrderStatus.READY_FOR_PICKUP:
            raise ValueError("El pedido no estÃ¡ listo para recoger")

        # Get delivery person
        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise ValueError("No eres un repartidor registrado")

        if order.deliveryPersonId and not self._ids_equal(
            order.deliveryPersonId, delivery_person.id
        ):
            raise ValueError("El pedido ya tiene un repartidor asignado")

        if delivery_person.currentOrderId and not self._ids_equal(
            delivery_person.currentOrderId, order_id
        ):
            raise ValueError("Ya tienes un pedido en curso")

        # Assign delivery person if it is not pre-assigned yet
        if not order.deliveryPersonId:
            estimated_time = datetime.utcnow() + timedelta(minutes=30)
            await self.orders_repo.assign_delivery_person(
                order_id, delivery_person.id, estimated_time
            )

        if not delivery_person.currentOrderId:
            await self.delivery_repo.assign_order(delivery_person.id, order_id)

        return await self.update_status(
            order_id,
            OrderStatus.READY_FOR_PICKUP,
            OrderActor.DELIVERY,
            f"Repartidor {delivery_person.name} asignado",
        )

    async def accept_order_for_payment(self, order_id: str, user_id: str) -> Order:
        """Delivery person accepts order before payment is enabled."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status != OrderStatus.AWAITING_DELIVERY_ACCEPTANCE:
            raise ValueError("El pedido no está esperando confirmación del mensajero")

        if order.deliveryPersonId:
            raise ValueError("El pedido ya fue tomado por otro mensajero")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise ValueError("No eres un repartidor registrado")

        reserved_order = await self.orders_repo.set_delivery_person(
            order_id, delivery_person.id
        )
        if not reserved_order:
            raise ValueError("No se pudo reservar el pedido para este mensajero")

        return await self.update_status(
            order_id,
            OrderStatus.PENDING_PAYMENT,
            OrderActor.DELIVERY,
            "Mensajero asignado. Esperando pago del cliente",
        )

    async def reject_order_for_payment(self, order_id: str, user_id: str) -> Order:
        """Delivery person rejects/relinquishes a pre-payment accepted order."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ValueError("El pedido no está en estado pendiente de pago")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person:
            raise ValueError("No eres un repartidor registrado")

        if not order.deliveryPersonId or not self._ids_equal(
            order.deliveryPersonId, delivery_person.id
        ):
            raise ValueError("No autorizado para rechazar este pedido")

        cleared_order = await self.orders_repo.clear_delivery_person(order_id)
        if not cleared_order:
            raise ValueError("No se pudo liberar el pedido")

        return await self.update_status(
            order_id,
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            OrderActor.DELIVERY,
            "Mensajero rechazó el pedido. Esperando otro mensajero",
        )

    async def confirm_pickup(self, order_id: str, user_id: str) -> Order:
        """Confirm order pickup from store (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status != OrderStatus.READY_FOR_PICKUP:
            raise ValueError("El pedido no está listo para recoger")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or not self._ids_equal(
            delivery_person.id, order.deliveryPersonId
        ):
            raise ValueError("No autorizado")

        if delivery_person.currentOrderId and not self._ids_equal(
            delivery_person.currentOrderId, order_id
        ):
            raise ValueError("Ya tienes otro pedido en curso")

        if not delivery_person.currentOrderId:
            await self.delivery_repo.assign_order(delivery_person.id, order_id)

        return await self.update_status(
            order_id,
            OrderStatus.ON_THE_WAY,
            OrderActor.DELIVERY,
            "Pedido recogido, en camino",
        )

    async def confirm_delivery(self, order_id: str, user_id: str) -> Order:
        """Confirm order delivery (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or not self._ids_equal(
            delivery_person.id, order.deliveryPersonId
        ):
            raise ValueError("No autorizado")

        # Complete delivery
        await self.delivery_repo.complete_delivery(delivery_person.id)

        # Update payment status if cash
        if order.paymentMethod == "cash":
            await self.orders_repo.update_payment_status(
                order_id, PaymentStatus.COMPLETED
            )

        return await self.update_status(
            order_id, OrderStatus.DELIVERED, OrderActor.DELIVERY, "Pedido entregado"
        )

    async def add_comment(self, order_id: str, user_id: str, message: str) -> Order:
        """Add a comment to an order."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Determine actor
        if self._ids_equal(order.customerId, user_id):
            actor = OrderActor.CUSTOMER
        else:
            branch = await branches_repo.get_by_id(order.branchId)
            business = await businesses_repo.get_by_id(order.businessId)
            manager_ids = {str(mid) for mid in branch.managerIds}
            if (
                self._ids_equal(business.ownerId, user_id)
                or str(user_id) in manager_ids
            ):
                actor = OrderActor.BUSINESS
            else:
                raise ValueError("No autorizado para comentar en este pedido")

        comment = OrderComment(
            id=str(uuid.uuid4()),
            author=actor,
            message=message,
            timestamp=datetime.utcnow(),
        )

        updated_order = await self.orders_repo.add_comment(order_id, comment)
        if not updated_order:
            raise ValueError("Error al agregar comentario")

        return updated_order

    async def rate_order(
        self, order_id: str, user_id: str, rating: int, comment: Optional[str] = None
    ) -> Order:
        """Rate a delivered order."""
        if rating < 1 or rating > 5:
            raise ValueError("La calificaciÃ³n debe ser entre 1 y 5")

        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
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

    async def get_order_tracking(self, order_id: str, user_id: str) -> dict:
        """Get order tracking information."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify access
        if not self._ids_equal(order.customerId, user_id):
            branch = await branches_repo.get_by_id(order.branchId)
            business = await businesses_repo.get_by_id(order.businessId)
            delivery_person = None
            if order.deliveryPersonId:
                delivery_person = await self.delivery_repo.get_by_id(
                    order.deliveryPersonId
                )

            manager_ids = {str(mid) for mid in branch.managerIds}
            is_authorized = (
                self._ids_equal(business.ownerId, user_id)
                or str(user_id) in manager_ids
                or (
                    delivery_person and self._ids_equal(delivery_person.userId, user_id)
                )
            )
            if not is_authorized:
                raise ValueError("No autorizado")

        # Get branch location
        branch = await branches_repo.get_by_id(order.branchId)
        store_location = {
            "longitude": branch.coordinates.coordinates[0],
            "latitude": branch.coordinates.coordinates[1],
        }

        # Get delivery location
        delivery_location = {
            "longitude": order.deliveryAddress.coordinates.coordinates[0],
            "latitude": order.deliveryAddress.coordinates.coordinates[1],
        }

        # Get delivery person location if assigned
        delivery_person_location = None
        if order.deliveryPersonId:
            delivery_person = await self.delivery_repo.get_by_id(order.deliveryPersonId)
            if delivery_person and delivery_person.currentLocation:
                delivery_person_location = {
                    "longitude": delivery_person.currentLocation.coordinates[0],
                    "latitude": delivery_person.currentLocation.coordinates[1],
                }

        # Calculate distance and ETA
        distance_km = None
        estimated_minutes = None
        if delivery_person_location:
            distance_km = haversine_distance(
                (
                    delivery_person_location["longitude"],
                    delivery_person_location["latitude"],
                ),
                (delivery_location["longitude"], delivery_location["latitude"]),
            )
            # Estimate 25 km/h average speed
            estimated_minutes = int((distance_km / 25) * 60)

        return {
            "order": order,
            "storeLocation": store_location,
            "deliveryLocation": delivery_location,
            "deliveryPersonLocation": delivery_person_location,
            "distanceKm": round(distance_km, 2) if distance_km else None,
            "estimatedMinutes": estimated_minutes,
        }

    async def _emit_tracking_event(self, order: Order):
        """
        Emit tracking event for real-time subscription.

        Called when order status changes or delivery location updates.
        Also sends push notification to customer.
        """
        try:
            # Import here to avoid circular dependency
            from schema.orders.subscriptions import publish_order_tracking
            from schema.orders.types import (
                CoordinatesType,
                OrderStatusEnum,
                OrderTrackingStreamPayload,
            )

            # Get delivery person location if assigned
            delivery_person_location = None
            distance_km = None
            estimated_minutes = None

            if order.deliveryPersonId:
                delivery_person = await self.delivery_repo.get_by_id(
                    order.deliveryPersonId
                )
                if delivery_person and delivery_person.currentLocation:
                    delivery_person_location = CoordinatesType(
                        type="Point",
                        coordinates=[
                            delivery_person.currentLocation.coordinates[0],
                            delivery_person.currentLocation.coordinates[1],
                        ],
                    )

                    # Calculate distance and ETA
                    from services.orders_utils import haversine_distance

                    distance_km = haversine_distance(
                        (
                            delivery_person.currentLocation.coordinates[0],
                            delivery_person.currentLocation.coordinates[1],
                        ),
                        (
                            order.deliveryAddress.coordinates.coordinates[0],
                            order.deliveryAddress.coordinates.coordinates[1],
                        ),
                    )
                    # Estimate 25 km/h average speed
                    estimated_minutes = int((distance_km / 25) * 60)

            # Calculate estimated minutes remaining from estimatedDeliveryTime
            estimated_minutes_remaining = None
            if order.estimatedDeliveryTime:
                remaining = (
                    order.estimatedDeliveryTime - datetime.utcnow()
                ).total_seconds() / 60
                estimated_minutes_remaining = max(0, int(remaining))

            # Create tracking payload
            tracking_payload = OrderTrackingStreamPayload(
                order_id=str(order.id),
                order_status=OrderStatusEnum(order.status.value),
                estimated_minutes_remaining=estimated_minutes_remaining,
                estimatedMinutes=estimated_minutes,
                distanceKm=round(distance_km, 2) if distance_km else None,
                deliveryPersonLocation=delivery_person_location,
            )

            # Publish to subscribers
            await publish_order_tracking(str(order.id), tracking_payload)

            print(
                f"[ORDER SERVICE] Emitted tracking event for order {order.id}, status: {order.status.value}"
            )

            # Send push notifications
            await self._send_order_status_notification(order)  # To customer
            await self._send_order_status_update_to_business(order)  # To business

        except Exception as e:
            # Don't fail the main operation if tracking event fails
            print(f"[ORDER SERVICE] Failed to emit tracking event: {e}")
            import traceback

            traceback.print_exc()

    async def _send_order_status_notification(self, order: Order):
        """Send push notification to customer about order status change."""
        try:
            from repositories.device_token_repository import device_token_repo
            from services.push_notification_service import push_service

            # Get customer's device tokens
            device_tokens = await device_token_repo.get_by_user_id(
                str(order.customerId)
            )

            if not device_tokens:
                print(f"[PUSH] No device tokens for customer {order.customerId}")
                return

            # Status-specific messages
            status_messages = {
                OrderStatus.ACCEPTED: {
                    "title": "Â¡Pedido aceptado! ðŸŽ‰",
                    "body": f"Tu pedido #{order.orderNumber} ha sido aceptado y se estÃ¡ preparando",
                },
                OrderStatus.PENDING_PAYMENT: {
                    "title": "Mensajero confirmado",
                    "body": f"Tu pedido #{order.orderNumber} ya puede pagarse",
                },
                OrderStatus.PREPARING: {
                    "title": "Preparando tu pedido ðŸ‘¨â€ðŸ³",
                    "body": f"Estamos preparando tu pedido #{order.orderNumber}",
                },
                OrderStatus.READY_FOR_PICKUP: {
                    "title": "Â¡Pedido listo! ðŸ“¦",
                    "body": f"Tu pedido #{order.orderNumber} estÃ¡ listo para ser recogido",
                },
                OrderStatus.ON_THE_WAY: {
                    "title": "Â¡En camino! ðŸš—",
                    "body": f"Tu pedido #{order.orderNumber} estÃ¡ en camino",
                },
                OrderStatus.DELIVERED: {
                    "title": "Â¡Pedido entregado! âœ…",
                    "body": f"Tu pedido #{order.orderNumber} ha sido entregado. Â¡DisfrÃºtalo!",
                },
                OrderStatus.CANCELLED: {
                    "title": "Pedido cancelado âŒ",
                    "body": f"Tu pedido #{order.orderNumber} ha sido cancelado",
                },
                OrderStatus.MODIFIED_BY_STORE: {
                    "title": "Pedido modificado âš ï¸",
                    "body": f"La tienda modificÃ³ tu pedido #{order.orderNumber}. Por favor revÃ­salo",
                },
            }

            notification = status_messages.get(order.status)
            if not notification:
                return

            # Group tokens by platform
            ios_tokens = [t.token for t in device_tokens if t.platform == "IOS"]
            android_tokens = [t.token for t in device_tokens if t.platform == "ANDROID"]

            # Additional data payload
            data = {
                "orderId": str(order.id),
                "orderNumber": order.orderNumber,
                "status": order.status.value,
                "type": "order_status_update",
            }

            # Send to iOS devices
            if ios_tokens:
                await push_service.send_to_all(
                    tokens=ios_tokens,
                    title=notification["title"],
                    body=notification["body"],
                    data=data,
                    platform="IOS",
                )
                print(f"[PUSH] Sent to {len(ios_tokens)} iOS devices")

            # Send to Android devices
            if android_tokens:
                await push_service.send_to_all(
                    tokens=android_tokens,
                    title=notification["title"],
                    body=notification["body"],
                    data=data,
                    platform="ANDROID",
                )
                print(f"[PUSH] Sent to {len(android_tokens)} Android devices")

        except Exception as e:
            # Don't fail the main operation if push notification fails
            print(f"[PUSH] Failed to send notification: {e}")
            import traceback

            traceback.print_exc()

    async def _send_new_order_notification_to_business(
        self, order: Order, branch, business
    ):
        """Send push notification to business managers/owner when new order arrives."""
        try:
            from repositories.device_token_repository import device_token_repo
            from services.push_notification_service import push_service

            # Collect user IDs to notify (owner + managers)
            user_ids_to_notify = [str(business.ownerId)]
            if hasattr(branch, "managerIds") and branch.managerIds:
                user_ids_to_notify.extend([str(mid) for mid in branch.managerIds])

            # Remove duplicates
            user_ids_to_notify = list(set(user_ids_to_notify))

            # Get device tokens for all managers/owner
            all_tokens = []
            for user_id in user_ids_to_notify:
                tokens = await device_token_repo.get_by_user_id(user_id)
                all_tokens.extend(tokens)

            if not all_tokens:
                print(
                    f"[PUSH] No device tokens for business {business.id} managers/owner"
                )
                return

            # Notification message
            title = "Â¡Nuevo pedido! ðŸ””"
            body = f"Pedido #{order.orderNumber} - ${order.total:.2f} - {len(order.items)} items"

            # Additional data payload
            data = {
                "orderId": str(order.id),
                "orderNumber": order.orderNumber,
                "branchId": str(order.branchId),
                "total": str(order.total),
                "status": order.status.value,
                "type": "new_order",
            }

            # Group tokens by platform
            ios_tokens = [t.token for t in all_tokens if t.platform == "IOS"]
            android_tokens = [t.token for t in all_tokens if t.platform == "ANDROID"]

            # Send to iOS devices
            if ios_tokens:
                await push_service.send_to_all(
                    tokens=ios_tokens, title=title, body=body, data=data, platform="IOS"
                )
                print(
                    f"[PUSH BUSINESS] New order sent to {len(ios_tokens)} iOS devices"
                )

            # Send to Android devices
            if android_tokens:
                await push_service.send_to_all(
                    tokens=android_tokens,
                    title=title,
                    body=body,
                    data=data,
                    platform="ANDROID",
                )
                print(
                    f"[PUSH BUSINESS] New order sent to {len(android_tokens)} Android devices"
                )

        except Exception as e:
            print(f"[PUSH BUSINESS] Failed to send new order notification: {e}")
            import traceback

            traceback.print_exc()

    async def _send_order_status_update_to_business(self, order: Order):
        """Send push notification to business managers/owner about order status updates."""
        try:
            from repositories.device_token_repository import device_token_repo
            from services.push_notification_service import push_service

            # Only notify business for specific status changes
            business_relevant_statuses = [
                OrderStatus.CANCELLED,  # Customer cancelled
                OrderStatus.DELIVERED,  # Delivery confirmed
            ]

            if order.status not in business_relevant_statuses:
                return

            # Get branch and business
            branch = await branches_repo.get_by_id(order.branchId)
            business = await businesses_repo.get_by_id(order.businessId)

            if not branch or not business:
                return

            # Collect user IDs to notify
            user_ids_to_notify = [str(business.ownerId)]
            if hasattr(branch, "managerIds") and branch.managerIds:
                user_ids_to_notify.extend([str(mid) for mid in branch.managerIds])

            user_ids_to_notify = list(set(user_ids_to_notify))

            # Get device tokens
            all_tokens = []
            for user_id in user_ids_to_notify:
                tokens = await device_token_repo.get_by_user_id(user_id)
                all_tokens.extend(tokens)

            if not all_tokens:
                return

            # Status-specific messages for business
            status_messages = {
                OrderStatus.CANCELLED: {
                    "title": "Pedido cancelado âŒ",
                    "body": f"Pedido #{order.orderNumber} ha sido cancelado",
                },
                OrderStatus.DELIVERED: {
                    "title": "Pedido entregado âœ…",
                    "body": f"Pedido #{order.orderNumber} fue entregado exitosamente",
                },
            }

            notification = status_messages.get(order.status)
            if not notification:
                return

            # Additional data payload
            data = {
                "orderId": str(order.id),
                "orderNumber": order.orderNumber,
                "branchId": str(order.branchId),
                "status": order.status.value,
                "type": "order_status_update_business",
            }

            # Group tokens by platform
            ios_tokens = [t.token for t in all_tokens if t.platform == "IOS"]
            android_tokens = [t.token for t in all_tokens if t.platform == "ANDROID"]

            # Send to iOS devices
            if ios_tokens:
                await push_service.send_to_all(
                    tokens=ios_tokens,
                    title=notification["title"],
                    body=notification["body"],
                    data=data,
                    platform="IOS",
                )
                print(
                    f"[PUSH BUSINESS] Status update sent to {len(ios_tokens)} iOS devices"
                )

            # Send to Android devices
            if android_tokens:
                await push_service.send_to_all(
                    tokens=android_tokens,
                    title=notification["title"],
                    body=notification["body"],
                    data=data,
                    platform="ANDROID",
                )
                print(
                    f"[PUSH BUSINESS] Status update sent to {len(android_tokens)} Android devices"
                )

        except Exception as e:
            print(f"[PUSH BUSINESS] Failed to send status update: {e}")
            import traceback

            traceback.print_exc()


order_service = OrderService()
