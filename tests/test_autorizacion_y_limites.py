"""Fase 1 de la auditoría (21 oct 2026): autorización de datos ajenos y límites de intentos.

- `users`/`user` solo admin (los gestores de negocio veían correo y teléfono de todos).
- `searchUsers`: para quien no es admin, 3 letras mínimo, correo enmascarado, sin
  teléfono ni saldo.
- `orderStats`/`dashboardStats`: solo admin o quien gestiona esa sucursal o negocio.
- Login y registro con límite por IP y por correo; correos sin distinguir mayúsculas.
- Código de entrega: como mucho 5 intentos fallidos por pedido.
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

import pytest

import schema.auth.mutations as auth_mutations
import schema.orders.queries as order_queries
import schema.users.queries as user_queries
import utils.rate_limit as rate_limit
from core.config import settings
from utils.auth import create_access_token

USER_ID = "507f1f77bcf86cd799439011"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(rate_limit, "redis_client", None)
    rate_limit._memory_fallback.clear()
    with patch.object(settings, "jwt_secret", "test-jwt-secret-fase1-0123456789abcdef"):
        yield


def _token(role: str) -> str:
    return create_access_token({"user_id": USER_ID, "role": role})


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None, "request": None}
    return info


def _usuario(email="ruben@gmail.com"):
    return SimpleNamespace(
        model_dump=None,
        wallet={"local": 500.0, "usd": 20.0},
        walletStatus="active",
        email=email,
    )


# ---------------------------------------------------------------- usuarios


@pytest.mark.parametrize("role", ["customer", "manager", "delivery"])
def test_users_y_user_solo_admin(monkeypatch, role):
    repo = SimpleNamespace(get_all=AsyncMock(return_value=[]), get_by_id=AsyncMock(return_value=None))
    monkeypatch.setattr(user_queries, "users_repo", repo)
    q = user_queries.UserQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(q.users(info=_info(), jwt=_token(role)))
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(q.user(info=_info(), id=USER_ID, jwt=_token(role)))
    repo.get_all.assert_not_awaited()


def test_search_users_enmascara_para_clientes(monkeypatch):
    repo = SimpleNamespace(search=AsyncMock(return_value=[_usuario()]))
    monkeypatch.setattr(user_queries, "users_repo", repo)
    monkeypatch.setattr(
        user_queries,
        "to_strawberry_dict",
        lambda u, exclude=None: {"email": u.email, "phone": "+5355555555"},
    )
    capturados = []
    monkeypatch.setattr(user_queries, "UserType", lambda **datos: capturados.append(datos) or datos)
    q = user_queries.UserQuery()

    assert asyncio.run(q.search_users(info=_info(), query="ru", jwt=_token("customer"))) == []
    repo.search.assert_not_awaited()

    asyncio.run(q.search_users(info=_info(), query="rub", jwt=_token("customer")))
    datos = capturados[-1]
    assert datos["email"] == "r***@gmail.com"
    assert datos["phone"] is None
    assert (datos["wallet"].local, datos["wallet"].usd) == (0.0, 0.0)
    repo.search.assert_awaited_with("rub", limit=20)

    asyncio.run(q.search_users(info=_info(), query="ru", jwt=_token("admin")))
    assert capturados[-1]["email"] == "ruben@gmail.com"
    assert capturados[-1]["phone"] == "+5355555555"


def test_enmascarar_correo():
    assert user_queries.enmascarar_correo("ana@x.com") == "a***@x.com"
    assert user_queries.enmascarar_correo(None) == ""
    assert user_queries.enmascarar_correo("sin-arroba") == ""


# ---------------------------------------------------------------- estadísticas


def _stats():
    return {
        "totalOrders": 0, "completedOrders": 0, "cancelledOrders": 0,
        "totalRevenue": 0.0, "averageOrderValue": 0.0, "averageDeliveryTime": 0.0,
        "topProducts": [],
    }


def test_order_stats_sin_sucursal_solo_admin(monkeypatch):
    repo = SimpleNamespace(get_stats=AsyncMock(return_value=_stats()))
    monkeypatch.setattr(order_queries, "orders_repo", repo)
    acceso = SimpleNamespace(require_branch_access=AsyncMock(side_effect=Exception("No autorizado")))
    monkeypatch.setattr(order_queries, "access_checker", acceso)
    q = order_queries.OrderQuery()
    hoy = datetime(2026, 10, 21)

    with pytest.raises(Exception, match="indica la sucursal"):
        asyncio.run(q.order_stats(info=_info(), fromDate=hoy, toDate=hoy, jwt=_token("manager")))
    with pytest.raises(Exception, match="No autorizado"):
        asyncio.run(q.order_stats(info=_info(), fromDate=hoy, toDate=hoy, jwt=_token("manager"), branchId="ajena"))
    repo.get_stats.assert_not_awaited()

    asyncio.run(q.order_stats(info=_info(), fromDate=hoy, toDate=hoy, jwt=_token("admin")))
    repo.get_stats.assert_awaited_once()


def test_dashboard_stats_exige_acceso_al_negocio(monkeypatch):
    repo = SimpleNamespace(get_dashboard_stats=AsyncMock(return_value=_stats()))
    monkeypatch.setattr(order_queries, "orders_repo", repo)
    acceso = SimpleNamespace(
        require_business_access=AsyncMock(side_effect=Exception("No autorizado para acceder a este negocio")),
        require_branch_access=AsyncMock(),
    )
    monkeypatch.setattr(order_queries, "access_checker", acceso)
    q = order_queries.OrderQuery()
    hoy = datetime(2026, 10, 21)
    with pytest.raises(Exception, match="No autorizado"):
        asyncio.run(q.dashboard_stats(info=_info(), businessId="otro", fromDate=hoy, toDate=hoy, jwt=_token("customer")))
    repo.get_dashboard_stats.assert_not_awaited()


# ---------------------------------------------------------------- login


def test_login_frena_tras_10_intentos_con_el_mismo_correo(monkeypatch):
    monkeypatch.setattr(auth_mutations, "auth_repo", SimpleNamespace(authenticate_user=AsyncMock(return_value=None)))
    m = auth_mutations.AuthMutation()
    entrada = SimpleNamespace(email="Victima@x.com", password="mala")
    for _ in range(10):
        with pytest.raises(Exception, match="Invalid email or password"):
            asyncio.run(m.login(info=_info(), input=entrada))
    with pytest.raises(Exception, match="Demasiados intentos"):
        asyncio.run(m.login(info=_info(), input=SimpleNamespace(email="victima@x.com", password="mala")))


def test_registro_guarda_el_correo_en_minusculas(monkeypatch):
    creado = SimpleNamespace(id=USER_ID, name="Ana", email="ana@x.com", phone=None, role="customer", createdAt=datetime(2026, 10, 21))
    repo = SimpleNamespace(get_user_by_email=AsyncMock(return_value=None), create_user=AsyncMock(return_value=creado))
    monkeypatch.setattr(auth_mutations, "auth_repo", repo)
    entrada = SimpleNamespace(name="Ana", email="  Ana@X.com ", password="secreta123", phone=None)
    asyncio.run(auth_mutations.AuthMutation().register(info=_info(), input=entrada))
    repo.get_user_by_email.assert_awaited_with("ana@x.com")
    assert repo.create_user.await_args.kwargs["email"] == "ana@x.com"


# ---------------------------------------------------------------- código de entrega


def test_codigo_de_entrega_se_bloquea_tras_5_fallos(monkeypatch):
    import services.orders_service as orders_service_mod
    from domain.orders import OrderStatus

    servicio = orders_service_mod.order_service
    pedido = SimpleNamespace(
        status=OrderStatus.ON_THE_WAY, deliveryPersonId="dp1", deliveryVerificationCode="4821", paymentMethod="cash"
    )
    monkeypatch.setattr(servicio, "orders_repo", SimpleNamespace(get_by_id=AsyncMock(return_value=pedido)))
    monkeypatch.setattr(servicio, "delivery_repo", SimpleNamespace(get_by_user_id=AsyncMock(return_value=SimpleNamespace(id="dp1"))))

    contador = {}

    class Coleccion:
        async def find_one(self, filtro):
            return contador.get(filtro["_id"])

        async def update_one(self, filtro, cambio, upsert=False):
            doc = contador.setdefault(filtro["_id"], {"failed": 0})
            doc["failed"] += cambio["$inc"]["failed"]

    with patch("clients.mongodb_client.get_database", return_value={"delivery_code_attempts": Coleccion()}):
        for _ in range(5):
            with pytest.raises(ValueError, match="incorrecto"):
                asyncio.run(servicio.confirm_delivery("pedido1", USER_ID, "0000"))
        with pytest.raises(ValueError, match="Demasiados intentos"):
            asyncio.run(servicio.confirm_delivery("pedido1", USER_ID, "4821"))
