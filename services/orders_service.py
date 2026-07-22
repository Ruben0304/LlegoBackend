"""Order service with business logic."""

import asyncio
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId

from core.config import settings
from domain.orders import (
    ALLOWED_TRANSITIONS,
    AddressType,
    DeliveryAddress,
    DeliveryPerson,
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
    VehicleType,
)
from repositories import (
    branches_repo,
    businesses_repo,
    combos_repo,
    payment_methods_repo,
    products_repo,
    showcases_repo,
    users_repo,
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
from utils.currency import branch_accepts_currency, normalize_currency


class OrderValidationError(ValueError):
    """Business validation error with stable GraphQL error code."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class OrderService:
    """Service for order business logic."""

    STATUS_TIMEOUT_MINUTES: Dict[OrderStatus, int] = {
        OrderStatus.PENDING_ACCEPTANCE: 15,
        OrderStatus.MODIFIED_BY_STORE: 15,
        OrderStatus.REJECTED_BY_STORE: 15,
        OrderStatus.AWAITING_DELIVERY_ACCEPTANCE: 15,
        OrderStatus.PENDING_PAYMENT: 15,
        OrderStatus.ACCEPTED: 20,
    }
    PRE_PREPARATION_TIMEOUT_STATUSES = set(STATUS_TIMEOUT_MINUTES.keys())
    CASH_PAYMENT_METHODS = {"cash", "efectivo", "cashondelivery", "contrareembolso"}
    NON_CASH_PAYMENT_METHODS = {
        "transfer",
        "transferencia",
        "transfermovil",
        "banktransfer",
        "wallet",
        "stripe",
        "card",
        "tarjeta",
        "gateway",
        "pasarela",
        "qvapay",
        "trondealer",
        "zelle",
        "crypto",
        "deposit",
    }

    def __init__(self):
        self.orders_repo = OrderRepository()
        self.delivery_repo = DeliveryPersonRepository()
        self.locations_repo = OrderLocationRepository()
        self._payment_cash_cache: Dict[str, bool] = {}

    async def _get_or_create_delivery_person(self, user_id: str) -> DeliveryPerson:
        """Return the delivery_persons record for this user, creating it on first use."""
        dp = await self.delivery_repo.get_by_user_id(user_id)
        if dp:
            return dp
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")
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
        return await self.delivery_repo.create(new_dp)

    @staticmethod
    def _ids_equal(a, b) -> bool:
        return str(a) == str(b)

    @classmethod
    def _next_deadline_for_status(
        cls, status: OrderStatus, now: Optional[datetime] = None
    ) -> Optional[datetime]:
        minutes = cls.STATUS_TIMEOUT_MINUTES.get(status)
        if minutes is None:
            return None
        base = now or datetime.utcnow()
        return base + timedelta(minutes=minutes)

    @staticmethod
    def _normalize_payment_token(value: Any) -> str:
        token = unicodedata.normalize("NFKD", str(value or ""))
        token = "".join(ch for ch in token if not unicodedata.combining(ch))
        token = re.sub(r"[^a-zA-Z0-9]+", "", token).lower()
        return token

    async def _is_cash_payment_method(self, payment_method: str) -> bool:
        """
        Resolve cash-vs-prepaid using payment method code/method metadata when available.

        Fallback is conservative: unknown methods are treated as non-cash.
        """
        normalized = self._normalize_payment_token(payment_method)
        if not normalized:
            return False

        if normalized in self._payment_cash_cache:
            return self._payment_cash_cache[normalized]

        if normalized in self.CASH_PAYMENT_METHODS:
            self._payment_cash_cache[normalized] = True
            return True
        if normalized in self.NON_CASH_PAYMENT_METHODS:
            self._payment_cash_cache[normalized] = False
            return False

        payment_method_doc = await payment_methods_repo.get_by_code(payment_method)
        if payment_method_doc:
            method_token = self._normalize_payment_token(
                getattr(payment_method_doc, "method", "")
            )
            code_token = self._normalize_payment_token(
                getattr(payment_method_doc, "code", "")
            )
            name_token = self._normalize_payment_token(
                getattr(payment_method_doc, "name", "")
            )

            is_cash = (
                method_token in self.CASH_PAYMENT_METHODS
                or code_token in self.CASH_PAYMENT_METHODS
                or "efectivo" in name_token
                or "cash" in name_token
            )
            if not is_cash and (
                method_token in self.NON_CASH_PAYMENT_METHODS
                or code_token in self.NON_CASH_PAYMENT_METHODS
            ):
                self._payment_cash_cache[normalized] = False
                return False

            self._payment_cash_cache[normalized] = is_cash
            return is_cash

        self._payment_cash_cache[normalized] = False
        return False

    @staticmethod
    def _generate_delivery_verification_code() -> str:
        # 6-digit code, enough entropy for delivery handoff while still user-friendly.
        return f"{uuid.uuid4().int % 1_000_000:06d}"

    @staticmethod
    def _timeout_cancel_message(status: OrderStatus) -> str:
        mapping = {
            OrderStatus.PENDING_ACCEPTANCE: (
                "Cancelado automaticamente: la tienda no respondio a tiempo"
            ),
            OrderStatus.MODIFIED_BY_STORE: (
                "Cancelado automaticamente: el cliente no reenvio el pedido modificado a tiempo"
            ),
            OrderStatus.REJECTED_BY_STORE: (
                "Cancelado automaticamente: el cliente no reenvio el pedido rechazado a tiempo"
            ),
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE: (
                "Cancelado automaticamente: ningun mensajero acepto a tiempo"
            ),
            OrderStatus.PENDING_PAYMENT: (
                "Cancelado automaticamente: el cliente no completo el pago a tiempo"
            ),
            OrderStatus.ACCEPTED: (
                "Cancelado automaticamente: la tienda no inicio la elaboracion a tiempo"
            ),
        }
        return mapping.get(status, "Cancelado automaticamente por expiracion")

    @staticmethod
    def _parse_time_to_minutes(time_value: Any) -> Optional[int]:
        raw = str(time_value or "").strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", raw):
            return None

        hour_str, minute_str = raw.split(":")
        hour = int(hour_str)
        minute = int(minute_str)

        if hour == 24 and minute == 0:
            return 24 * 60
        if hour < 0 or hour > 23:
            return None
        if minute < 0 or minute > 59:
            return None
        return hour * 60 + minute

    @staticmethod
    def _python_weekday_to_schedule_day(python_weekday: int) -> int:
        """Convert Python weekday (Mon=0..Sun=6) to schedule day (Dom=0..Sab=6)."""
        return (python_weekday + 1) % 7

    @classmethod
    def _get_day_sched(cls, schedule: Any, schedule_day: int) -> Any:
        """Return the DaySchedule (model or dict) for a given schedule day, or None."""
        days = schedule.days if hasattr(schedule, "days") else schedule.get("days", [])
        for d in days:
            day_num = d.day if hasattr(d, "day") else d.get("day")
            if day_num == schedule_day:
                return d
        return None

    @classmethod
    def _day_sched_hours(cls, day_sched: Any) -> List[tuple[int, int]]:
        """Extract list of (start_min, end_min) tuples from a DaySchedule."""
        hours = (
            day_sched.hours if hasattr(day_sched, "hours") else day_sched.get("hours", [])
        )
        result: List[tuple[int, int]] = []
        for tr in hours:
            open_str = tr.open if hasattr(tr, "open") else tr.get("open", "")
            close_str = tr.close if hasattr(tr, "close") else tr.get("close", "")
            start = cls._parse_time_to_minutes(open_str)
            end = cls._parse_time_to_minutes(close_str)
            if start is not None and end is not None:
                result.append((start, end))
        return result

    @classmethod
    def _format_schedule_for_day(cls, schedule: Any, target_python_weekday: int) -> str:
        if not schedule:
            return "no configurado"

        target_day = cls._python_weekday_to_schedule_day(target_python_weekday)
        day_sched = cls._get_day_sched(schedule, target_day)
        if not day_sched:
            return "cerrado"

        is_open = (
            day_sched.isOpen if hasattr(day_sched, "isOpen") else day_sched.get("isOpen", True)
        )
        if not is_open:
            return "cerrado"

        ranges = cls._day_sched_hours(day_sched)
        if not ranges:
            return "cerrado"

        return ", ".join(f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for s, e in ranges)

    @staticmethod
    def _get_branch_local_now() -> datetime:
        try:
            return datetime.now(ZoneInfo("America/Havana"))
        except Exception:
            return datetime.now()

    @classmethod
    def _is_branch_open_now(cls, schedule: Any, now_local: datetime) -> bool:
        if not schedule:
            return True

        # Check temporary status override
        ts = (
            schedule.temporaryStatus
            if hasattr(schedule, "temporaryStatus")
            else schedule.get("temporaryStatus")
        )
        if ts:
            if ts.temporallyClosed if hasattr(ts, "temporallyClosed") else ts.get("temporallyClosed", False):
                return False
            if ts.temporallyOpen if hasattr(ts, "temporallyOpen") else ts.get("temporallyOpen", False):
                return True

        current_minutes = now_local.hour * 60 + now_local.minute
        today = cls._python_weekday_to_schedule_day(now_local.weekday())
        yesterday = (today - 1) % 7

        today_sched = cls._get_day_sched(schedule, today)
        if today_sched:
            is_open = (
                today_sched.isOpen
                if hasattr(today_sched, "isOpen")
                else today_sched.get("isOpen", True)
            )
            if is_open:
                for start, end in cls._day_sched_hours(today_sched):
                    if start == 0 and end == 24 * 60:
                        return True
                    if start < end and start <= current_minutes < end:
                        return True
                    if start > end and current_minutes >= start:  # overnight start
                        return True

        # Overnight ranges inherited from yesterday (e.g. 22:00-02:00)
        yesterday_sched = cls._get_day_sched(schedule, yesterday)
        if yesterday_sched:
            is_open = (
                yesterday_sched.isOpen
                if hasattr(yesterday_sched, "isOpen")
                else yesterday_sched.get("isOpen", True)
            )
            if is_open:
                for start, end in cls._day_sched_hours(yesterday_sched):
                    if start > end and current_minutes < end:
                        return True

        return False

    @classmethod
    def _is_branch_open_at(cls, schedule: Any, target_local: datetime) -> bool:
        """Check if branch is open at a specific future datetime (ignores temporaryStatus)."""
        if not schedule:
            return True

        target_minutes = target_local.hour * 60 + target_local.minute
        target_day = cls._python_weekday_to_schedule_day(target_local.weekday())

        day_sched = cls._get_day_sched(schedule, target_day)
        if not day_sched:
            return False

        is_open = (
            day_sched.isOpen if hasattr(day_sched, "isOpen") else day_sched.get("isOpen", True)
        )
        if not is_open:
            return False

        for start, end in cls._day_sched_hours(day_sched):
            if start == 0 and end == 24 * 60:
                return True
            if start < end and start <= target_minutes < end:
                return True
            if start > end and (target_minutes >= start or target_minutes < end):  # overnight
                return True

        return False

    @staticmethod
    def _coerce_bool(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            val = value.strip().lower()
            if val in {"true", "1", "yes"}:
                return True
            if val in {"false", "0", "no"}:
                return False
        return None

    def _is_branch_open_for_pickup(self, schedule: Any) -> bool:
        """Validate pickup availability using branch local time and shared schedule parser."""
        if not schedule:
            return True

        now_local = self._get_branch_local_now()
        return self._is_branch_open_now(schedule, now_local)

    def _assert_pickup_item_eligible(self, entity: Any, label: str) -> None:
        direct_flags = [
            getattr(entity, "pickupEligible", None),
            getattr(entity, "isPickupEligible", None),
            getattr(entity, "pickupEnabled", None),
            getattr(entity, "isPickupEnabled", None),
            getattr(entity, "pickupAvailable", None),
            getattr(entity, "isPickupAvailable", None),
            getattr(entity, "availableForPickup", None),
        ]
        for flag in direct_flags:
            coerced = self._coerce_bool(flag)
            if coerced is False:
                raise OrderValidationError(
                    f"{label} no es elegible para recogida en tienda",
                    code="ITEM_NOT_PICKUP_ELIGIBLE",
                )

        negative_flags = [
            getattr(entity, "deliveryOnly", None),
            getattr(entity, "requiresDelivery", None),
        ]
        for flag in negative_flags:
            coerced = self._coerce_bool(flag)
            if coerced is True:
                raise OrderValidationError(
                    f"{label} no es elegible para recogida en tienda",
                    code="ITEM_NOT_PICKUP_ELIGIBLE",
                )

    @staticmethod
    def _resolve_order_destination_coords(
        order: Any, branch_coords: Optional[List[float]] = None
    ) -> List[float]:
        if getattr(order, "deliveryMode", None) == "pickup":
            if (
                getattr(order, "pickupAddress", None)
                and order.pickupAddress.coordinates
            ):
                return list(order.pickupAddress.coordinates.coordinates)
            if branch_coords:
                return list(branch_coords)

        if (
            getattr(order, "deliveryAddress", None)
            and order.deliveryAddress.coordinates
        ):
            return list(order.deliveryAddress.coordinates.coordinates)

        if branch_coords:
            return list(branch_coords)

        return [0.0, 0.0]

    @staticmethod
    def _normalize_currency(currency: Optional[str], fallback: str = "USD") -> str:
        return normalize_currency(currency, fallback=fallback)

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

    @classmethod
    def _resolve_order_exchange_rate(cls, order: Any, branch: Any) -> Optional[float]:
        """Tasa a usar al recalcular un pedido existente (modificacion/reenvio).

        Prioriza la tasa que quedo congelada en el pedido al crearlo, para que
        un cambio posterior de `branch.exchangeRate` no altere retroactivamente
        el total de un pedido que el cliente ya acepto. Solo cae a la tasa
        actual de la sucursal para pedidos legados que no tienen snapshot.
        """
        frozen_rate = getattr(order, "exchangeRate", None)
        if frozen_rate is not None:
            try:
                value = float(frozen_rate)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        return cls._resolve_exchange_rate(branch)

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
                "Falta exchangeRate valido en la sucursal para convertir monedas"
            )

        if from_curr == "USD" and to_curr == "CUP":
            return value * exchange_rate
        if from_curr == "CUP" and to_curr == "USD":
            return value / exchange_rate
        raise ValueError(f"Conversion de moneda no soportada: {from_curr} -> {to_curr}")

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
        fulfillment_type: str = "DELIVERY",
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
                if fulfillment_type == "PICKUP":
                    self._assert_pickup_item_eligible(
                        product, f"Producto {product.name}"
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
        fulfillment_type: str = "DELIVERY",
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
            if fulfillment_type == "PICKUP":
                self._assert_pickup_item_eligible(product, f"Producto {product.name}")

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
            if fulfillment_type == "PICKUP":
                self._assert_pickup_item_eligible(combo, f"Combo {combo.name}")

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
                fulfillment_type=fulfillment_type,
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
            if fulfillment_type == "PICKUP":
                self._assert_pickup_item_eligible(showcase, f"Vitrina {showcase.title}")

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
        delivery_address: Optional[dict],
        payment_method: str,
        payment_intent_id: Optional[str] = None,
        promo_code: Optional[str] = None,
        initial_comment: Optional[str] = None,
        fulfillment_type: Optional[str] = None,
        pickup_branch_id: Optional[str] = None,
        pickup_window_id: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> Order:
        """Create a new order with all validations."""
        requested_fulfillment = (fulfillment_type or "DELIVERY").strip().upper()
        if requested_fulfillment not in {"DELIVERY", "PICKUP"}:
            raise OrderValidationError(
                "Tipo de fulfillment inválido",
                code="INVALID_FULFILLMENT_INPUT",
            )
        is_pickup = requested_fulfillment == "PICKUP"

        if is_pickup:
            if delivery_address is not None:
                raise OrderValidationError(
                    "deliveryAddress debe ser null para pickup",
                    code="INVALID_FULFILLMENT_INPUT",
                )
            if not pickup_branch_id:
                raise OrderValidationError(
                    "pickupBranchId es requerido para pickup",
                    code="INVALID_FULFILLMENT_INPUT",
                )
            if str(pickup_branch_id) != str(branch_id):
                raise OrderValidationError(
                    "pickupBranchId debe ser igual a branchId en esta fase",
                    code="INVALID_FULFILLMENT_INPUT",
                )
        else:
            if not delivery_address:
                raise OrderValidationError(
                    "deliveryAddress es requerido para delivery",
                    code="INVALID_FULFILLMENT_INPUT",
                )

        # 1. Validate branch exists and is active
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise ValueError("Sucursal no encontrada")
        if not branch.isActive:
            raise ValueError("La sucursal no está activa")
        if branch.catalogOnly:
            raise ValueError("Esta sucursal solo muestra su catálogo y no acepta pedidos")
        if getattr(branch, "acceptingOrders", True) is False:
            raise OrderValidationError(
                "La sucursal pausó temporalmente la recepción de pedidos. Inténtalo más tarde.",
                code="BRANCH_NOT_ACCEPTING_ORDERS",
            )

        # Validate business is approved
        from repositories import businesses_repo
        business = await businesses_repo.get_by_id(str(branch.businessId))
        if not business or business.approvalStatus != "approved":
            raise OrderValidationError(
                "Este negocio no está disponible para recibir pedidos",
                code="BUSINESS_NOT_APPROVED",
            )
        if not items:
            raise ValueError("El pedido debe incluir al menos un ítem")

        day_names = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

        if scheduled_for is not None:
            # Validate scheduled time
            branch_now = self._get_branch_local_now()
            try:
                scheduled_local = scheduled_for.astimezone(ZoneInfo("America/Havana"))
            except Exception:
                scheduled_local = scheduled_for

            if scheduled_local <= branch_now:
                raise OrderValidationError(
                    "La hora programada debe ser en el futuro",
                    code="INVALID_SCHEDULED_TIME",
                )

            today_date = branch_now.date()
            tomorrow_date = today_date + timedelta(days=1)
            scheduled_date = scheduled_local.date()
            if scheduled_date not in {today_date, tomorrow_date}:
                raise OrderValidationError(
                    "Solo se pueden programar pedidos para hoy o mañana",
                    code="INVALID_SCHEDULED_TIME",
                )

            if not self._is_branch_open_at(branch.schedule, scheduled_local):
                target_schedule = self._format_schedule_for_day(
                    branch.schedule, scheduled_local.weekday()
                )
                raise OrderValidationError(
                    f"La sucursal no está abierta a las {scheduled_local.strftime('%H:%M')} "
                    f"({day_names[scheduled_local.weekday()]}). "
                    f"Horario: {target_schedule}",
                    code="BRANCH_CLOSED_AT_SCHEDULED_TIME",
                )
        else:
            if not is_pickup:
                branch_now = self._get_branch_local_now()
                if not self._is_branch_open_now(branch.schedule, branch_now):
                    day_index = branch_now.weekday()
                    today_schedule = self._format_schedule_for_day(
                        branch.schedule, day_index
                    )
                    raise ValueError(
                        "La sucursal esta cerrada en este momento "
                        f"({day_names[day_index]} {branch_now.strftime('%H:%M')}). "
                        f"Horario de hoy: {today_schedule}"
                    )

        # 2. Get business
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            raise ValueError("Negocio no encontrado")

        if is_pickup and scheduled_for is None:
            if not self._is_branch_open_for_pickup(getattr(branch, "schedule", None)):
                raise OrderValidationError(
                    "La sucursal está cerrada para pickup",
                    code="BRANCH_CLOSED_FOR_PICKUP",
                )

        # 2.5. Resolve payment method and monetary context
        (
            payment_method_code,
            payment_method_currency,
            payment_method_doc,
        ) = await self._resolve_payment_method(payment_method)

        # Every branch decides independently which currencies it accepts
        # (CUP-only, USD-only, or both with its own manual exchange rate) and
        # which catalog payment methods it actually offers, so a method that
        # is valid globally can still be invalid for this specific branch.
        if payment_method_doc:
            if not branch_accepts_currency(
                getattr(branch, "acceptedCurrency", None), payment_method_doc.currency
            ):
                raise OrderValidationError(
                    f"La sucursal no acepta pagos en {payment_method_doc.currency}",
                    code="PAYMENT_METHOD_CURRENCY_NOT_ACCEPTED",
                )

            configured_method_ids = {
                str(pm_id) for pm_id in (getattr(branch, "paymentMethodIds", None) or [])
            }
            if (
                configured_method_ids
                and str(payment_method_doc.id) not in configured_method_ids
            ):
                raise OrderValidationError(
                    "La sucursal no tiene habilitado este método de pago",
                    code="PAYMENT_METHOD_NOT_AVAILABLE",
                )

        order_currency = self._resolve_order_currency(branch, payment_method_currency)
        exchange_rate = self._resolve_exchange_rate(branch)

        if is_pickup and payment_method_doc:
            payment_pickup_enabled = self._coerce_bool(
                getattr(payment_method_doc, "pickupEnabled", None)
            )
            payment_delivery_only = self._coerce_bool(
                getattr(payment_method_doc, "deliveryOnly", None)
            )
            if payment_pickup_enabled is False or payment_delivery_only is True:
                raise OrderValidationError(
                    "Método de pago no permitido para pickup",
                    code="FULFILLMENT_PAYMENT_METHOD_NOT_ALLOWED",
                )

        # 3. Validate and snapshot items in order currency
        order_items: List[OrderItem] = []
        subtotal = 0.0

        for item in items:
            try:
                order_item, line_subtotal = await self._build_order_item_snapshot(
                    item=item,
                    branch_id=branch_id,
                    order_currency=order_currency,
                    exchange_rate=exchange_rate,
                    fulfillment_type=requested_fulfillment,
                )
            except OrderValidationError:
                raise
            except ValueError as e:
                if is_pickup:
                    message = str(e)
                    message_lc = message.lower()
                    code = "ITEM_NOT_PICKUP_ELIGIBLE"
                    if "no disponible" in message_lc:
                        code = "PICKUP_STOCK_UNAVAILABLE"
                    raise OrderValidationError(message, code=code)
                raise
            order_items.append(order_item)
            subtotal += line_subtotal

        subtotal = round(subtotal, 2)

        # 4. Calculate delivery fee using H3 zones (zone config in CUP)
        branch_coords = (
            branch.coordinates.coordinates[0],
            branch.coordinates.coordinates[1],
        )
        if is_pickup:
            delivery_fee = 0.0
            delivery_zone_id = None
            delivery_mode = "pickup"
        else:
            delivery_coords = (
                delivery_address["longitude"],
                delivery_address["latitude"],
            )

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
        service_charge = round(subtotal * settings.service_fee_rate, 2)
        total = round(subtotal + delivery_fee + service_charge - total_discounts, 2)

        # 6. Payment status starts as PENDING for all methods.
        # For stripe, the PaymentIntent is created later via initiatePayment()
        # once the order reaches PENDING_PAYMENT status (after business + delivery accept).
        payment_status = PaymentStatus.PENDING

        # 7. Create order
        now = datetime.utcnow()
        order_id = str(ObjectId())
        order_number = await generate_order_number(
            branch_code=branch.code or "suc",
            branch_id=str(branch.id),
        )

        if is_pickup:
            # Legacy fallback: keep deliveryAddress non-null for old tracking clients.
            delivery_addr = DeliveryAddress(
                street=branch.address or "Recogida en tienda",
                city=None,
                reference="pickup",
                coordinates=GeoPoint(
                    type="Point",
                    coordinates=list(branch.coordinates.coordinates),
                ),
                addressType=AddressType.OTHER,
                buildingName=None,
                floor=None,
                apartment=None,
                deliveryInstructions=None,
            )
        else:
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
            serviceCharge=service_charge,
            deliveryMode=delivery_mode,
            deliveryZoneId=delivery_zone_id,
            branchH3=branch_h3,
            discounts=discounts,
            total=total,
            currency=order_currency,
            exchangeRate=exchange_rate,
            status=OrderStatus.PENDING_ACCEPTANCE,
            deliveryAddress=delivery_addr,
            pickupAddress=pickup_addr,
            timeline=timeline,
            comments=comments,
            paymentMethod=payment_method_code,
            paymentStatus=payment_status,
            paymentId=payment_intent_id,
            deadlineAt=self._next_deadline_for_status(
                OrderStatus.PENDING_ACCEPTANCE, now
            ),
            scheduledFor=scheduled_for,
            resubmissionCount=0,
            createdAt=now,
            updatedAt=now,
            lastStatusAt=now,
        )

        created_order = await self.orders_repo.create(order)

        # 8. Send push notification to branch managers/owner
        await self._send_new_order_notification_to_business(
            created_order, branch, business
        )

        # 9. Demo mode: auto-progress order if placed at the demo store
        if getattr(branch, "isDemoStore", False):
            order_id_str = str(created_order.id)
            asyncio.create_task(
                self._demo_auto_progress(
                    order_id=order_id_str,
                    payment_method_code=payment_method_code,
                    is_pickup=is_pickup,
                )
            )

        return created_order

    # ------------------------------------------------------------------
    # DEMO MODE  (App Store review account)
    # ------------------------------------------------------------------

    async def _demo_auto_progress(
        self, order_id: str, payment_method_code: str, is_pickup: bool
    ) -> None:
        """Auto-progress a demo-store order through all statuses so Apple's
        reviewer can experience the full flow without any manual store action.

        Timeline (approximate):
          +4 s  → store accepts (PENDING_ACCEPTANCE → next)
          +4 s  → delivery person assigned if delivery mode
          +6 s  → ACCEPTED (payment auto-completed for Stripe)
          +6 s  → PREPARING
          +8 s  → READY_FOR_PICKUP  (pickup) / ON_THE_WAY (delivery)
        """
        try:
            # --- Step 1: store auto-accepts after a realistic pause ---
            await asyncio.sleep(4)

            order = await self.orders_repo.get_by_id(order_id)
            if not order or order.status != OrderStatus.PENDING_ACCEPTANCE:
                return

            is_cash = payment_method_code.lower() in self.CASH_PAYMENT_METHODS

            if is_pickup:
                # pickup + cash → ACCEPTED directly (standard iOS flow)
                # pickup + stripe → PENDING_PAYMENT (iOS will call initiatePayment)
                next_status = (
                    OrderStatus.ACCEPTED if is_cash else OrderStatus.PENDING_PAYMENT
                )
            else:
                # delivery → always AWAITING_DELIVERY_ACCEPTANCE first
                next_status = OrderStatus.AWAITING_DELIVERY_ACCEPTANCE

            await self.update_status(
                order_id,
                next_status,
                OrderActor.SYSTEM,
                "[Demo] Pedido aceptado automáticamente por la tienda",
                extra_fields={"estimatedMinutes": 10},
            )

            # --- Step 2: for delivery, auto-assign a courier ---
            if not is_pickup:
                await asyncio.sleep(4)
                order = await self.orders_repo.get_by_id(order_id)
                if not order or order.status != OrderStatus.AWAITING_DELIVERY_ACCEPTANCE:
                    return

                # cash delivery → ACCEPTED; stripe delivery → PENDING_PAYMENT
                courier_next = (
                    OrderStatus.ACCEPTED if is_cash else OrderStatus.PENDING_PAYMENT
                )
                await self.update_status(
                    order_id,
                    courier_next,
                    OrderActor.SYSTEM,
                    "[Demo] Mensajero asignado automáticamente",
                )

            # --- Step 3: for Stripe, auto-complete payment so no card entry needed ---
            if not is_cash:
                await asyncio.sleep(3)
                order = await self.orders_repo.get_by_id(order_id)
                if not order or order.status != OrderStatus.PENDING_PAYMENT:
                    return

                from clients.mongodb_client import get_database
                db = get_database()
                try:
                    oid = ObjectId(order_id)
                except Exception:
                    oid = order_id

                await db.orders.update_one(
                    {"_id": oid, "status": "pending_payment"},
                    {
                        "$set": {
                            "paymentStatus": "completed",
                            "paidAt": datetime.utcnow(),
                            "status": "accepted",
                            "updatedAt": datetime.utcnow(),
                        }
                    },
                )
                # Refresh local var so the rest of the flow continues correctly
                order = await self.orders_repo.get_by_id(order_id)
                if not order or order.status != OrderStatus.ACCEPTED:
                    return

            # --- Step 4: move through PREPARING ---
            await asyncio.sleep(6)
            order = await self.orders_repo.get_by_id(order_id)
            if not order or order.status != OrderStatus.ACCEPTED:
                return

            await self.update_status(
                order_id,
                OrderStatus.PREPARING,
                OrderActor.SYSTEM,
                "[Demo] Preparando tu pedido",
                force=True,  # bypass payment check since we already completed it
            )

            # --- Step 5: final status (READY_FOR_PICKUP or ON_THE_WAY) ---
            await asyncio.sleep(8)
            order = await self.orders_repo.get_by_id(order_id)
            if not order or order.status != OrderStatus.PREPARING:
                return

            final_status = (
                OrderStatus.READY_FOR_PICKUP if is_pickup else OrderStatus.ON_THE_WAY
            )
            await self.update_status(
                order_id,
                final_status,
                OrderActor.SYSTEM,
                "[Demo] Pedido listo" if is_pickup else "[Demo] Pedido en camino",
            )

        except Exception as exc:  # noqa: BLE001
            # Never let background task crash silently
            import logging
            logging.getLogger(__name__).warning(
                "[Demo] Auto-progress failed for order %s: %s", order_id, exc
            )

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
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """Update order status with validation."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        now = datetime.utcnow()

        if not force:
            pickup_direct_accept = (
                getattr(order, "deliveryMode", None) == "pickup"
                and order.status == OrderStatus.PENDING_ACCEPTANCE
                and new_status in {OrderStatus.PENDING_PAYMENT, OrderStatus.ACCEPTED}
            )
            if not pickup_direct_accept and not self._validate_transition(
                order.status, new_status
            ):
                raise ValueError(
                    f"Transicion de estado no permitida: {order.status.value} -> {new_status.value}"
                )

        # Payment is mandatory before PREPARING for non-cash methods.
        if (
            new_status == OrderStatus.PREPARING
            and not await self._is_cash_payment_method(order.paymentMethod)
            and order.paymentStatus != PaymentStatus.COMPLETED
        ):
            raise ValueError(
                "El pedido debe estar pagado antes de prepararse. "
                "El cliente debe completar el pago primero."
            )

        if not message:
            messages = {
                OrderStatus.AWAITING_DELIVERY_ACCEPTANCE: "Pedido aceptado por tienda, esperando mensajero",
                OrderStatus.ACCEPTED: "Pedido aceptado por la tienda",
                OrderStatus.PENDING_PAYMENT: "Mensajero confirmado. Pedido listo para pagar",
                OrderStatus.PREPARING: "Tu pedido esta siendo preparado",
                OrderStatus.READY_FOR_PICKUP: "Pedido listo para recoger",
                OrderStatus.ON_THE_WAY: "Tu pedido esta en camino",
                OrderStatus.DELIVERED: "Pedido entregado",
                OrderStatus.CANCELLED: "Pedido cancelado",
                OrderStatus.MODIFIED_BY_STORE: "La tienda ha modificado tu pedido",
                OrderStatus.REJECTED_BY_STORE: "La tienda rechazo tu pedido",
                OrderStatus.PENDING_ACCEPTANCE: "Pedido reenviado, esperando respuesta de la tienda",
            }
            message = messages.get(
                new_status, f"Estado actualizado a {new_status.value}"
            )

        extra_set_fields: Dict[str, Any] = {
            "deadlineAt": self._next_deadline_for_status(new_status, now)
        }
        if new_status == OrderStatus.CANCELLED and order.paymentStatus not in {
            PaymentStatus.COMPLETED
        }:
            extra_set_fields["paymentStatus"] = PaymentStatus.CANCELLED.value
        if extra_fields:
            extra_set_fields.update(extra_fields)
        if new_status in {OrderStatus.ON_THE_WAY, OrderStatus.READY_FOR_PICKUP} and not order.deliveryVerificationCode:
            extra_set_fields["deliveryVerificationCode"] = (
                self._generate_delivery_verification_code()
            )
            extra_set_fields["deliveryCodeGeneratedAt"] = now
            extra_set_fields["deliveryCodeAttempts"] = 0
        if new_status == OrderStatus.DELIVERED:
            extra_set_fields["deliveryCodeVerifiedAt"] = now

        timeline_entry = OrderTimeline(
            status=new_status,
            timestamp=now,
            message=message,
            actor=actor,
        )

        updated_order = await self.orders_repo.update_status(
            order_id,
            new_status,
            timeline_entry,
            extra_set_fields=extra_set_fields,
        )

        if not updated_order:
            raise ValueError("Error al actualizar el pedido")

        # Count customer delivered orders exactly once per order.
        if new_status == OrderStatus.DELIVERED:
            customer_id = await self.orders_repo.mark_delivered_counted_for_customer(
                order_id
            )
            if customer_id:
                await users_repo.increment_delivered_orders_count(customer_id)

        # When an order is cancelled or delivered, free the delivery person so
        # they can accept the next order. Covers auto-cancel by the scheduler,
        # manual cancel by customer/admin, and normal delivery completion.
        if new_status in {OrderStatus.CANCELLED, OrderStatus.DELIVERED}:
            if order.deliveryPersonId:
                await self.delivery_repo.complete_delivery(str(order.deliveryPersonId))

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
                raise ValueError("El precio de envio no puede ser negativo")
            total_discounts = sum(d.amount for d in order.discounts)
            new_total = round(
                order.subtotal + delivery_fee_override + order.serviceCharge - total_discounts, 2
            )
            await self.orders_repo.update_delivery_fee(
                order_id, delivery_fee_override, new_total, delivery_mode="branch"
            )

        if order.deliveryMode == "pickup":
            next_status = (
                OrderStatus.ACCEPTED
                if await self._is_cash_payment_method(order.paymentMethod)
                else OrderStatus.PENDING_PAYMENT
            )
            message = f"Pedido aceptado para pickup. Tiempo estimado: {estimated_minutes} minutos"
        else:
            next_status = OrderStatus.AWAITING_DELIVERY_ACCEPTANCE
            message = (
                "Pedido aceptado por tienda. Esperando mensajero. "
                f"Tiempo estimado: {estimated_minutes} minutos"
            )

        return await self.update_status(
            order_id,
            next_status,
            OrderActor.BUSINESS,
            message,
            extra_fields={"estimatedMinutes": estimated_minutes},
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
            OrderStatus.REJECTED_BY_STORE,
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
        exchange_rate = self._resolve_order_exchange_rate(order, branch)
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

        # Recalculate total (service charge recalculated on new subtotal)
        total_discounts = sum(d.amount for d in order.discounts)
        service_charge = round(subtotal * settings.service_fee_rate, 2)
        total = round(subtotal + order.deliveryFee + service_charge - total_discounts, 2)

        timeline_entry = OrderTimeline(
            status=OrderStatus.MODIFIED_BY_STORE,
            timestamp=datetime.utcnow(),
            message=f"Pedido modificado: {reason}",
            actor=OrderActor.BUSINESS,
        )

        updated_order = await self.orders_repo.update_items(
            order_id, modified_items, round(subtotal, 2), service_charge, total, timeline_entry
        )

        if not updated_order:
            raise ValueError("Error al modificar el pedido")

        # TODO: Send push notification to customer

        # Emit tracking event for real-time subscription
        await self._emit_tracking_event(updated_order)

        return updated_order

    async def accept_modifications(self, order_id: str, user_id: str) -> Order:
        """Accept store modifications and resubmit for branch confirmation."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        if order.status != OrderStatus.MODIFIED_BY_STORE:
            raise ValueError("El pedido no tiene modificaciones pendientes")

        return await self.resubmit_order(
            order_id,
            user_id,
            comment="Cliente acepto modificaciones y reenvio el pedido",
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

        return await self.update_status(
            order_id,
            OrderStatus.CANCELLED,
            OrderActor.CUSTOMER,
            "Cliente rechazo modificaciones y abandono el pedido",
        )

    async def resubmit_order(
        self,
        order_id: str,
        user_id: str,
        new_items: Optional[List[dict]] = None,
        comment: Optional[str] = None,
    ) -> Order:
        """Customer resubmits the order to the initial review state."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        allowed_statuses = {
            OrderStatus.MODIFIED_BY_STORE,
            OrderStatus.REJECTED_BY_STORE,
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            OrderStatus.PENDING_PAYMENT,
        }
        if order.status not in allowed_statuses:
            raise ValueError("El pedido no puede reenviarse en este estado")

        branch = await branches_repo.get_by_id(order.branchId)
        if not branch:
            raise ValueError("Sucursal no encontrada")
        exchange_rate = self._resolve_order_exchange_rate(order, branch)
        order_currency = self._normalize_currency(order.currency, fallback="USD")

        updated_items: Optional[List[OrderItem]] = None
        subtotal_value: Optional[float] = None
        service_charge_value: Optional[float] = None
        total_value: Optional[float] = None

        if new_items is not None:
            rebuilt_items: List[OrderItem] = []
            running_subtotal = 0.0
            for item in new_items:
                order_item, line_subtotal = await self._build_order_item_snapshot(
                    item=item,
                    branch_id=str(order.branchId),
                    order_currency=order_currency,
                    exchange_rate=exchange_rate,
                )
                rebuilt_items.append(order_item)
                running_subtotal += line_subtotal

            total_discounts = sum(d.amount for d in order.discounts)
            subtotal_value = round(running_subtotal, 2)
            service_charge_value = round(subtotal_value * settings.service_fee_rate, 2)
            total_value = round(subtotal_value + order.deliveryFee + service_charge_value - total_discounts, 2)
            updated_items = rebuilt_items

        timeline_message = (
            comment or ""
        ).strip() or "Cliente reenvio el pedido para una nueva revision de la tienda"
        timeline_entry = OrderTimeline(
            status=OrderStatus.PENDING_ACCEPTANCE,
            timestamp=datetime.utcnow(),
            message=timeline_message,
            actor=OrderActor.CUSTOMER,
        )

        updated_order = await self.orders_repo.resubmit_order(
            order_id,
            timeline_entry,
            items=updated_items,
            subtotal=subtotal_value,
            service_charge=service_charge_value,
            total=total_value,
        )
        if not updated_order:
            raise ValueError("No se pudo reenviar el pedido")

        await self._emit_tracking_event(updated_order)
        return updated_order

    async def cancel_order(
        self, order_id: str, user_id: str, reason: Optional[str] = None
    ) -> Order:
        """Cancel an order (customer action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if not self._ids_equal(order.customerId, user_id):
            raise ValueError("No autorizado")

        # Customer can explicitly abandon only editable pre-preparation flows.
        cancellable_statuses = [
            OrderStatus.MODIFIED_BY_STORE,
            OrderStatus.REJECTED_BY_STORE,
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
        """Backward-compatible courier accept entrypoint."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Preferred flow: courier accepts before payment.
        if order.status == OrderStatus.AWAITING_DELIVERY_ACCEPTANCE:
            return await self.accept_order_for_payment(order_id, user_id)

        # Idempotency: if the order is already in a post-acceptance status and
        # this courier is the assigned delivery person, return the current state.
        # This handles retries when the first response was lost in transit.
        if order.status in {
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.ACCEPTED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.ON_THE_WAY,
        }:
            delivery_person = await self.delivery_repo.get_by_user_id(user_id)
            if delivery_person and order.deliveryPersonId and self._ids_equal(
                order.deliveryPersonId, delivery_person.id
            ):
                print(f"[COURIER] accept_delivery idempotent return — already accepted, status={order.status.value}")
                return order

        # Legacy flow support: assign courier once order is ready for pickup.
        if order.status not in {OrderStatus.READY_FOR_PICKUP, OrderStatus.PREPARING}:
            raise ValueError("El pedido no esta listo para recogida")

        delivery_person = await self._get_or_create_delivery_person(user_id)

        if order.deliveryPersonId and not self._ids_equal(
            order.deliveryPersonId, delivery_person.id
        ):
            raise ValueError("El pedido ya tiene un repartidor asignado")

        if delivery_person.currentOrderId and not self._ids_equal(
            delivery_person.currentOrderId, order_id
        ):
            raise ValueError("Ya tienes un pedido en curso")

        if not order.deliveryPersonId:
            estimated_time = datetime.utcnow() + timedelta(minutes=30)
            await self.orders_repo.assign_delivery_person(
                order_id, delivery_person.id, estimated_time
            )

        if not delivery_person.currentOrderId:
            await self.delivery_repo.assign_order(delivery_person.id, order_id)

        refreshed = await self.orders_repo.get_by_id(order_id)
        if not refreshed:
            raise ValueError("Error al actualizar asignacion de mensajero")
        return refreshed

    async def accept_order_for_payment(self, order_id: str, user_id: str) -> Order:
        """Delivery person accepts order before payment is enabled."""
        print(f"[COURIER] accept_order_for_payment order={order_id} user={user_id}")
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        print(f"[COURIER] order status={order.status.value} deliveryPersonId={order.deliveryPersonId}")

        # Resolve delivery person first so we can do idempotency checks.
        delivery_person = await self._get_or_create_delivery_person(user_id)
        print(f"[COURIER] delivery_person id={delivery_person.id}")

        # Idempotency: if this courier already accepted this order (i.e. a previous
        # request succeeded on the backend but the response was lost in transit),
        # just return the current order state instead of erroring.
        if order.deliveryPersonId and self._ids_equal(order.deliveryPersonId, delivery_person.id):
            print(f"[COURIER] accept_order_for_payment idempotent — already accepted, status={order.status.value}")
            return order

        if order.status != OrderStatus.AWAITING_DELIVERY_ACCEPTANCE:
            raise ValueError("El pedido no está esperando confirmación del mensajero")

        if order.deliveryPersonId:
            raise ValueError("El pedido ya fue tomado por otro mensajero")

        reserved_order = await self.orders_repo.set_delivery_person(
            order_id, delivery_person.id
        )
        if not reserved_order:
            # Could be a race between two couriers. Reload and check who won.
            order_check = await self.orders_repo.get_by_id(order_id)
            if order_check and order_check.deliveryPersonId and self._ids_equal(
                order_check.deliveryPersonId, delivery_person.id
            ):
                print(f"[COURIER] set_delivery_person race — we won on a previous tick, continuing")
                reserved_order = order_check
            else:
                raise ValueError("El pedido ya fue tomado por otro mensajero")

        await self.delivery_repo.assign_order(delivery_person.id, order_id)

        is_cash = await self._is_cash_payment_method(order.paymentMethod)
        print(f"[COURIER] paymentMethod={order.paymentMethod} is_cash={is_cash}")
        if is_cash:
            next_status = OrderStatus.ACCEPTED
            next_message = "Mensajero asignado. Pago en efectivo, el negocio puede iniciar elaboracion"
        else:
            next_status = OrderStatus.PENDING_PAYMENT
            next_message = "Mensajero asignado. Esperando pago del cliente"

        print(f"[COURIER] transitioning to next_status={next_status.value}")
        result = await self.update_status(
            order_id,
            next_status,
            OrderActor.DELIVERY,
            next_message,
        )
        print(f"[COURIER] accept_order_for_payment done — final status={result.status.value} deliveryPersonId={result.deliveryPersonId}")
        return result

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

        if order.status not in {
            OrderStatus.ACCEPTED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
        }:
            raise ValueError("El pedido no esta listo para recogida")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or not self._ids_equal(
            delivery_person.id, order.deliveryPersonId
        ):
            raise ValueError("No autorizado")

        if delivery_person.currentOrderId and not self._ids_equal(
            delivery_person.currentOrderId, order_id
        ):
            # Only block if the other order is genuinely still active
            other_order = await self.orders_repo.get_by_id(
                str(delivery_person.currentOrderId)
            )
            if other_order and other_order.status not in {
                OrderStatus.DELIVERED,
                OrderStatus.CANCELLED,
            }:
                raise ValueError("Ya tienes otro pedido en curso")

        if not delivery_person.currentOrderId or not self._ids_equal(
            delivery_person.currentOrderId, order_id
        ):
            await self.delivery_repo.assign_order(delivery_person.id, order_id)

        return await self.update_status(
            order_id,
            OrderStatus.ON_THE_WAY,
            OrderActor.DELIVERY,
            "Pedido recogido, en camino",
        )

    async def confirm_delivery(
        self, order_id: str, user_id: str, delivery_code: str
    ) -> Order:
        """Confirm order delivery (delivery person action)."""
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        if order.status != OrderStatus.ON_THE_WAY:
            raise ValueError("El pedido no esta en camino")

        delivery_person = await self.delivery_repo.get_by_user_id(user_id)
        if not delivery_person or not self._ids_equal(
            delivery_person.id, order.deliveryPersonId
        ):
            raise ValueError("No autorizado")

        expected_code = (order.deliveryVerificationCode or "").strip()
        provided_code = (delivery_code or "").strip()
        if not expected_code:
            raise ValueError("No hay codigo de entrega generado para este pedido")
        if provided_code != expected_code:
            raise ValueError("Codigo de entrega incorrecto")

        # Complete delivery
        await self.delivery_repo.complete_delivery(delivery_person.id)

        # Update payment status if cash
        if await self._is_cash_payment_method(order.paymentMethod):
            await self.orders_repo.update_payment_status(
                order_id, PaymentStatus.COMPLETED
            )

        return await self.update_status(
            order_id, OrderStatus.DELIVERED, OrderActor.DELIVERY, "Pedido entregado"
        )

    async def expire_stale_pre_preparation_orders(self, limit: int = 100) -> int:
        """Auto-cancel timed-out orders before PREPARING."""
        expired_orders = await self.orders_repo.get_expired_preparation_candidates(
            statuses=list(self.PRE_PREPARATION_TIMEOUT_STATUSES),
            now=datetime.utcnow(),
            limit=limit,
        )
        expired_count = 0
        for order in expired_orders:
            try:
                await self.update_status(
                    str(order.id),
                    OrderStatus.CANCELLED,
                    OrderActor.SYSTEM,
                    self._timeout_cancel_message(order.status),
                )
                expired_count += 1
            except ValueError:
                # Race-safe: if status changed concurrently, skip it.
                continue
        return expired_count

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
            raise ValueError("La calificacion debe ser entre 1 y 5")

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
        delivery_coords = self._resolve_order_destination_coords(
            order, branch_coords=branch.coordinates.coordinates
        )
        delivery_location = {
            "longitude": delivery_coords[0],
            "latitude": delivery_coords[1],
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
                        tuple(
                            self._resolve_order_destination_coords(
                                order,
                                branch_coords=order.pickupAddress.coordinates.coordinates
                                if order.pickupAddress
                                else None,
                            )
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
                    "title": "Pedido aceptado",
                    "body": f"Tu pedido #{order.orderNumber} ha sido aceptado y se esta preparando",
                },
                OrderStatus.PENDING_PAYMENT: {
                    "title": "Mensajero confirmado",
                    "body": f"Tu pedido #{order.orderNumber} ya puede pagarse",
                },
                OrderStatus.PREPARING: {
                    "title": "Preparando tu pedido",
                    "body": f"Estamos preparando tu pedido #{order.orderNumber}",
                },
                OrderStatus.READY_FOR_PICKUP: {
                    "title": "Pedido listo",
                    "body": f"Tu pedido #{order.orderNumber} esta listo para ser recogido",
                },
                OrderStatus.ON_THE_WAY: {
                    "title": "En camino",
                    "body": f"Tu pedido #{order.orderNumber} esta en camino",
                },
                OrderStatus.DELIVERED: {
                    "title": "Pedido entregado",
                    "body": f"Tu pedido #{order.orderNumber} ha sido entregado. Disfrutalo",
                },
                OrderStatus.CANCELLED: {
                    "title": "Pedido cancelado",
                    "body": f"Tu pedido #{order.orderNumber} ha sido cancelado",
                },
                OrderStatus.MODIFIED_BY_STORE: {
                    "title": "Pedido modificado",
                    "body": f"La tienda modifico tu pedido #{order.orderNumber}. Por favor revisalo",
                },
                OrderStatus.REJECTED_BY_STORE: {
                    "title": "Pedido rechazado",
                    "body": f"La tienda rechazo tu pedido #{order.orderNumber}. Puedes editarlo y reenviarlo",
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
            title = "Nuevo pedido"
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
                    "title": "Pedido cancelado",
                    "body": f"Pedido #{order.orderNumber} ha sido cancelado",
                },
                OrderStatus.DELIVERED: {
                    "title": "Pedido entregado",
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
