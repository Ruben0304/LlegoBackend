"""Endpoints de soporte para la suite E2E (tests/e2e).

Solo existen dentro del sandbox E2E (header `X-E2E-Key` valido, ver
core/sandbox.py): fuera de el responden 404. Todo lo que escriben va a la base
de datos del sandbox, nunca a produccion.

- GET    /e2e/ping                      comprueba que el sandbox esta activo
- POST   /e2e/world                     crea un "mundo" aislado (negocio, sucursal,
                                        productos, metodos de pago, usuarios+tokens)
- POST   /e2e/orders/{id}/expire        simula que vencio el plazo del pedido y
                                        ejecuta la misma logica del worker de timeouts
- PATCH  /e2e/branches/{id}             cambia el estado de la sucursal a mitad de
                                        un flujo (pausa pedidos, cierra, desactiva)
- DELETE /e2e/sandbox                   borra la base de datos del sandbox

Los documentos se insertan directo en Mongo (no via repositorios) para no
disparar efectos compartidos con produccion (indexado en Qdrant, cache...).
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from clients.mongodb_client import get_database
from core.config import settings
from core.sandbox import is_sandbox, sandbox_database_name
from domain.orders import OrderStatus
from utils.auth import create_access_token

router = APIRouter(prefix="/e2e", tags=["E2E sandbox"])

# Centro de La Habana; la direccion de entrega queda a ~1 km.
BRANCH_COORDS = [-82.3830, 23.1136]
DELIVERY_COORDS = [-82.3750, 23.1180]

ROLES = ("customer", "customer2", "owner", "staff", "courier", "courier2", "stranger", "admin")


def require_sandbox() -> None:
    if not is_sandbox():
        # 404 y no 403: fuera del sandbox estos endpoints "no existen".
        raise HTTPException(status_code=404, detail="Not Found")


class WorldOptions(BaseModel):
    acceptedCurrency: str = "CUP"
    pickupEnabled: bool = True
    acceptingOrders: bool = True
    alwaysOpen: bool = True


class BranchPatch(BaseModel):
    acceptingOrders: Optional[bool] = None
    isActive: Optional[bool] = None
    catalogOnly: Optional[bool] = None
    temporarilyClosed: Optional[bool] = None


def _open_all_week_schedule() -> dict:
    return {
        "days": [
            {"day": d, "isOpen": True, "hours": [{"open": "00:00", "close": "24:00"}]}
            for d in range(7)
        ],
        "temporaryStatus": None,
    }


def _closed_all_week_schedule() -> dict:
    return {
        "days": [{"day": d, "isOpen": False, "hours": []} for d in range(7)],
        "temporaryStatus": None,
    }


@router.get("/ping", dependencies=[Depends(require_sandbox)])
async def ping():
    return {"sandbox": True, "database": sandbox_database_name()}


@router.post("/world", dependencies=[Depends(require_sandbox)])
async def create_world(options: WorldOptions = WorldOptions()):
    db = get_database()
    now = datetime.utcnow()
    tag = secrets.token_hex(4)

    users = {}
    for role in ROLES:
        user_id = ObjectId()
        jwt_role = "admin" if role == "admin" else (
            "merchant" if role in {"owner", "staff"} else "customer"
        )
        email = f"e2e+{tag}-{role}@llego.test"
        await db.users.insert_one(
            {
                "_id": user_id,
                "name": f"E2E {role} {tag}",
                "email": email,
                "username": f"e2e_{tag}_{role}",
                "phone": f"+535{secrets.randbelow(10**7):07d}",
                "role": jwt_role,
                "wallet": {"local": 0.0, "usd": 0.0},
                "walletStatus": "active",
                "authProvider": "local",
                "location": {"type": "Point", "coordinates": DELIVERY_COORDS},
                "createdAt": now,
                "e2eTag": tag,
            }
        )
        users[role] = {
            "id": str(user_id),
            # Firmado con el secreto del sandbox: no sirve en produccion.
            "token": create_access_token(
                {"sub": email, "user_id": str(user_id), "role": jwt_role},
                expires_delta=timedelta(hours=6),
            ),
        }

    currency = options.acceptedCurrency.upper()
    method_currency = "USD" if currency == "USD" else "CUP"
    payment_methods = {}
    for key, method, name in (
        ("cash", "cash", "Efectivo"),
        ("transfer", "transfer", "Transferencia"),
    ):
        pm_id = ObjectId()
        await db.payment_methods.insert_one(
            {
                "_id": pm_id,
                "name": f"{name} E2E {tag}",
                # Codigo unico por mundo; el tipo real lo decide `method`.
                "code": f"{key}_e2e_{tag}",
                "currency": method_currency,
                "method": method,
                "commissionPercent": 0.0,
                "deliveryFeePercent": 0.0,
                "isRefundable": True,
                "requiresProof": method == "transfer",
                "requiresBusinessConfirmation": method == "transfer",
                "expirationMinutes": None,
                "isActive": True,
                "displayOrder": 0,
                "createdAt": now,
                "updatedAt": now,
                "e2eTag": tag,
            }
        )
        payment_methods[key] = {"id": str(pm_id), "code": f"{key}_e2e_{tag}"}

    async def _create_business(owner_id: str, suffix: str) -> ObjectId:
        business_id = ObjectId()
        await db.bussisnes.insert_one(  # coleccion mal escrita a proposito (ver CLAUDE.md)
            {
                "_id": business_id,
                "name": f"Negocio E2E {suffix} {tag}",
                "ownerId": ObjectId(owner_id),
                "globalRating": 5.0,
                "avatar": "e2e/avatar.png",
                "isActive": True,
                "approvalStatus": "approved",
                "approvedAt": now,
                "createdAt": now,
                "e2eTag": tag,
            }
        )
        return business_id

    async def _create_branch(business_id: ObjectId, manager_ids: list, suffix: str) -> ObjectId:
        branch_id = ObjectId()
        await db.branches.insert_one(
            {
                "_id": branch_id,
                "businessId": business_id,
                "name": f"Sucursal E2E {suffix} {tag}",
                "address": "Calle 23 esq. L, Vedado",
                "coordinates": {"type": "Point", "coordinates": BRANCH_COORDS},
                "phone": "+5350000000",
                "schedule": _open_all_week_schedule()
                if options.alwaysOpen
                else _closed_all_week_schedule(),
                "managerIds": [ObjectId(m) for m in manager_ids],
                "isActive": True,
                "tipos": ["restaurante"],
                "paymentMethodIds": [ObjectId(pm["id"]) for pm in payment_methods.values()],
                "wallet": {"local": 0.0, "usd": 0.0},
                "walletStatus": "active",
                "useAppMessaging": True,
                "catalogOnly": False,
                "acceptingOrders": options.acceptingOrders,
                "pickupEnabled": options.pickupEnabled,
                "acceptedCurrency": currency,
                "exchangeRate": 400,
                "accounts": [],
                "code": f"e2e{suffix}",
                "isDemoStore": False,
                "createdAt": now,
                "e2eTag": tag,
            }
        )
        return branch_id

    business_id = await _create_business(users["owner"]["id"], "a")
    branch_id = await _create_branch(
        business_id, [users["owner"]["id"], users["staff"]["id"]], "a"
    )
    # Otro negocio (con su propio dueno ficticio) para probar aislamiento.
    other_business_id = await _create_business(users["stranger"]["id"], "b")
    other_branch_id = await _create_branch(other_business_id, [users["stranger"]["id"]], "b")

    products = {}
    for key, branch, price, available in (
        ("burger", branch_id, 500.0, True),
        ("soda", branch_id, 150.0, True),
        ("unavailable", branch_id, 300.0, False),
        ("foreign", other_branch_id, 200.0, True),
    ):
        product_id = ObjectId()
        await db.products.insert_one(
            {
                "_id": product_id,
                "branchId": branch,
                "name": f"{key.capitalize()} E2E {tag}",
                "description": "Producto de prueba E2E",
                "weight": "1u",
                "price": price,
                "currency": method_currency,
                "image": "e2e/product.png",
                "availability": available,
                "variantListIds": [],
                "createdAt": now,
                "e2eTag": tag,
            }
        )
        products[key] = {"id": str(product_id), "price": price}

    return {
        "tag": tag,
        "currency": method_currency,
        "businessId": str(business_id),
        "branchId": str(branch_id),
        "otherBranchId": str(other_branch_id),
        "products": products,
        "paymentMethods": payment_methods,
        "users": users,
        "deliveryAddress": {
            "street": "Calle 25 #1060 e/ 10 y 12, Vedado",
            "latitude": DELIVERY_COORDS[1],
            "longitude": DELIVERY_COORDS[0],
            "reference": "Casa verde",
        },
        "serviceFeeRate": settings.service_fee_rate,
    }


@router.post("/orders/{order_id}/expire", dependencies=[Depends(require_sandbox)])
async def expire_order(order_id: str):
    """Pone el deadline del pedido en el pasado y ejecuta la logica del worker
    de timeouts SOLO para ese pedido."""
    from services.orders_service import order_service

    db = get_database()
    try:
        oid = ObjectId(order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="orderId invalido") from exc

    candidate = await order_service.orders_repo.get_by_id(order_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if (
        candidate.status not in order_service.PRE_PREPARATION_TIMEOUT_STATUSES
        or not candidate.deadlineAt
    ):
        result = "no_deadline"
    else:
        # Igual que el worker: se decide sobre un "candidato" leido antes, y el
        # vencimiento solo se aplica si el pedido sigue en ese estado. Si en
        # paralelo cambio (la tienda acepto, el cliente pago...), no se toca.
        past = datetime.utcnow() - timedelta(minutes=1)
        forced = await db.orders.update_one(
            {"_id": oid, "status": candidate.status.value},
            {"$set": {"deadlineAt": past}},
        )
        if forced.matched_count == 0:
            result = "skipped"
        else:
            candidate.deadlineAt = past
            result = await order_service.expire_order(candidate)

    order = await order_service.orders_repo.get_by_id(order_id)
    return {
        "result": result,
        "status": order.status.value,
        "paymentStatus": order.paymentStatus.value,
        "requiresAttention": order.requiresAttention,
        "attentionReason": order.attentionReason,
    }


@router.patch("/branches/{branch_id}", dependencies=[Depends(require_sandbox)])
async def patch_branch(branch_id: str, patch: BranchPatch):
    db = get_database()
    updates = {}
    if patch.acceptingOrders is not None:
        updates["acceptingOrders"] = patch.acceptingOrders
    if patch.isActive is not None:
        updates["isActive"] = patch.isActive
    if patch.catalogOnly is not None:
        updates["catalogOnly"] = patch.catalogOnly
    if patch.temporarilyClosed is not None:
        updates["schedule"] = (
            _closed_all_week_schedule()
            if patch.temporarilyClosed
            else _open_all_week_schedule()
        )
    if not updates:
        raise HTTPException(status_code=400, detail="Nada que actualizar")
    result = await db.branches.update_one({"_id": ObjectId(branch_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return {"updated": list(updates.keys())}


@router.delete("/sandbox", dependencies=[Depends(require_sandbox)])
async def drop_sandbox():
    """Borra TODA la base del sandbox (nunca la de produccion)."""
    name = sandbox_database_name()  # lanza si coincidiera con produccion
    db = get_database()
    if db.name != name or name == settings.mongodb_database:
        raise HTTPException(status_code=500, detail="Sandbox mal configurado")
    await db.client.drop_database(name)
    return {"dropped": name}
