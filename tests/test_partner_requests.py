"""Registro de socios: solicitudes para vender en Llegó o ser mensajero.

Cubre services/partner_requests_service.py y schema/partner_requests/:
envío (teléfono normalizado, email de la cuenta, una sola solicitud activa por
tipo), permisos del Panel Admin y lo que da aprobar o rechazar (mensajero
aprobado en delivery_persons, negocios pendientes aprobados).

La mayoría usa repositorios mockeados. Los tests marcados "Mongo real" usan una
base de datos temporal en MONGODB_URL (se borran al terminar) y se saltan si no
hay Mongo: son los que comprueban el índice único parcial y el upsert del
registro de mensajero, que con mocks no se pueden probar.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
from pymongo.errors import DuplicateKeyError

import schema.partner_requests.mutations as pr_mutations
import schema.partner_requests.queries as pr_queries
import services.partner_requests_service as service
from core.config import settings
from domain.partner_requests import (
    PartnerRequest,
    PartnerRequestKind,
    PartnerRequestStatus,
)
from schema.partner_requests.inputs import SubmitPartnerRequestInput
from schema.partner_requests.types import (
    PartnerRequestStatusEnum,
    PartnerRequestTypeEnum,
)
from utils.auth import create_access_token
from utils.phone import normalize_phone

USER_ID = "507f1f77bcf86cd799439021"
ADMIN_ID = "507f1f77bcf86cd799439022"
REQUEST_ID = "507f1f77bcf86cd799439023"


def run(coro):
    return asyncio.run(coro)


def _request(kind=PartnerRequestKind.COURIER, status=PartnerRequestStatus.PENDING, **extra):
    now = datetime.now(timezone.utc)
    data = {
        "_id": REQUEST_ID,
        "userId": USER_ID,
        "type": kind,
        "status": status,
        "fullName": "Ana Pérez",
        "phone": "+5355555555",
        "email": "ana@example.com",
        "active": status in (PartnerRequestStatus.PENDING, PartnerRequestStatus.CONTACTED),
        "adminNotes": "Llamar por la tarde",
        "reviewedBy": ADMIN_ID,
        "createdAt": now,
        "updatedAt": now,
        **extra,
    }
    return PartnerRequest(**data)


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _jwt(role="customer", user_id=USER_ID):
    return create_access_token({"user_id": user_id, "role": role})


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-partner-requests")


@pytest.fixture
def repos(monkeypatch):
    """Repositorios que toca el servicio, todos mockeados."""
    created = {}

    async def _create(data):
        created.update(data)
        return _request(
            kind=data["type"],
            phone=data["phone"],
            fullName=data["fullName"],
            email=data["email"],
            businessName=data["businessName"],
            municipality=data["municipality"],
            notes=data["notes"],
        )

    partner = SimpleNamespace(
        create=AsyncMock(side_effect=_create),
        get_active_for_user=AsyncMock(return_value=None),
        get_latest_for_user=AsyncMock(return_value=None),
        exists_with_status=AsyncMock(return_value=False),
        get_by_id=AsyncMock(return_value=None),
        update_status=AsyncMock(),
        list_requests=AsyncMock(return_value=[]),
        count_requests=AsyncMock(return_value=0),
    )
    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(email="ana@example.com"))
    )
    couriers = SimpleNamespace(
        get_by_user_id=AsyncMock(return_value=None),
        approve_user=AsyncMock(),
        revoke_user=AsyncMock(),
    )
    approve_businesses = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "partner_requests_repo", partner)
    monkeypatch.setattr(service, "users_repo", users)
    monkeypatch.setattr(service, "delivery_persons_repo", couriers)
    monkeypatch.setattr(service, "approve_pending_businesses_of_owner", approve_businesses)
    # has_courier_access (myPartnerAccess) lee el registro por su propio import.
    import services.courier_access as courier_access

    monkeypatch.setattr(courier_access, "delivery_persons_repo", couriers)
    return SimpleNamespace(
        partner=partner,
        users=users,
        couriers=couriers,
        approve_businesses=approve_businesses,
        created=created,
    )


# ------------------------------------------------------------------- teléfono


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("55555555", "+5355555555"),
        ("5555 5555", "+5355555555"),
        ("5555-5555", "+5355555555"),
        ("+53 5555 5555", "+5355555555"),
        ("53 55555555", "+5355555555"),
        ("0053 5555 5555", "+5355555555"),
        ("055555555", "+5355555555"),
        ("78345678", "+5378345678"),  # fijo de La Habana
        ("+1 (305) 555-1234", "+13055551234"),
        ("0034 600 000 000", "+34600000000"),
    ],
)
def test_normalize_phone_valid(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "123", "5555555", "555555555", "+53 555", "+5355555555555", "abc", "5555 55a5", "+0 1234 5678"],
)
def test_normalize_phone_invalid(raw):
    assert normalize_phone(raw) is None


# --------------------------------------------------------------------- envío


def test_submit_normalizes_phone_and_keeps_account_email(repos):
    request = run(
        service.submit_partner_request(
            USER_ID,
            PartnerRequestKind.BUSINESS,
            full_name="  Ana Pérez ",
            phone="5555 5555",
            business_name=" Cafetería Ana ",
            municipality="Plaza",
            notes="  ",
        )
    )
    assert repos.created["phone"] == "+5355555555"
    assert repos.created["fullName"] == "Ana Pérez"
    assert repos.created["businessName"] == "Cafetería Ana"
    assert repos.created["notes"] is None
    assert repos.created["email"] == "ana@example.com"
    assert repos.created["type"] == PartnerRequestKind.BUSINESS
    assert request.phone == "+5355555555"


def test_submit_courier_drops_business_name(repos):
    run(
        service.submit_partner_request(
            USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", "55555555",
            business_name="No aplica", municipality="Cerro",
        )
    )
    assert repos.created["businessName"] is None
    assert repos.created["municipality"] == "Cerro"


@pytest.mark.parametrize("phone", ["123", "5555555", "+53 12", "teléfono"])
def test_submit_rejects_invalid_phone_with_clear_message(repos, phone):
    with pytest.raises(ValueError, match="teléfono no es válido"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", phone))
    repos.partner.create.assert_not_awaited()


def test_submit_requires_phone_and_name(repos):
    with pytest.raises(ValueError, match="teléfono es obligatorio"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", " "))
    with pytest.raises(ValueError, match="nombre completo"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, " ", "55555555"))


def test_submit_rejects_duplicate_active_request(repos):
    repos.partner.get_active_for_user.return_value = _request(
        status=PartnerRequestStatus.CONTACTED, phone="+5355551234"
    )
    with pytest.raises(ValueError, match=r"Ya tienes una solicitud pendiente.*\+5355551234"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", "55555555"))
    repos.partner.create.assert_not_awaited()


def test_submit_concurrent_duplicate_is_friendly(repos):
    """Dos envíos a la vez: el índice único parcial frena el segundo."""
    repos.partner.create.side_effect = DuplicateKeyError("dup")
    with pytest.raises(ValueError, match="Ya tienes una solicitud pendiente"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", "55555555"))


def test_submit_allowed_again_after_rejection(repos):
    """Solo cuenta la solicitud activa: tras un rechazo se puede volver a pedir."""
    repos.partner.get_latest_for_user.return_value = _request(status=PartnerRequestStatus.REJECTED)
    run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", "55555555"))
    repos.partner.create.assert_awaited_once()


@pytest.mark.parametrize("approved", [True, None])
def test_submit_courier_when_already_courier_is_rejected(repos, approved):
    record = SimpleNamespace(id="dp-1")
    if approved is not None:
        record.approved = approved
    repos.couriers.get_by_user_id.return_value = record
    with pytest.raises(ValueError, match="ya está aprobada como mensajero"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.COURIER, "Ana Pérez", "55555555"))


def test_submit_business_when_already_approved_is_rejected(repos):
    repos.partner.exists_with_status.return_value = True
    with pytest.raises(ValueError, match="ya está aprobada para vender"):
        run(service.submit_partner_request(USER_ID, PartnerRequestKind.BUSINESS, "Ana Pérez", "55555555"))


def test_submit_resolver_requires_jwt_and_hides_admin_fields(repos):
    mutation = pr_mutations.PartnerRequestMutation()
    payload = SubmitPartnerRequestInput(
        type=PartnerRequestTypeEnum.COURIER, fullName="Ana Pérez", phone="55555555"
    )
    with pytest.raises(Exception, match="Autenticación requerida"):
        run(mutation.submit_partner_request(info=_info(), input=payload, jwt=""))

    result = run(mutation.submit_partner_request(info=_info(), input=payload, jwt=_jwt()))
    assert result.type == PartnerRequestTypeEnum.COURIER
    assert result.status == PartnerRequestStatusEnum.PENDING
    assert result.phone == "+5355555555"
    # Las notas internas y el revisor no son para el solicitante.
    assert result.adminNotes is None
    assert result.reviewedBy is None


def test_submit_resolver_surfaces_validation_message(repos):
    mutation = pr_mutations.PartnerRequestMutation()
    payload = SubmitPartnerRequestInput(
        type=PartnerRequestTypeEnum.BUSINESS, fullName="Ana Pérez", phone="12"
    )
    with pytest.raises(Exception, match="teléfono no es válido"):
        run(mutation.submit_partner_request(info=_info(), input=payload, jwt=_jwt()))


# ------------------------------------------------------------- myPartnerAccess


def test_my_partner_access_reports_access_and_latest_requests(repos):
    repos.couriers.get_by_user_id.return_value = SimpleNamespace(id="dp-1", approved=True)
    repos.partner.exists_with_status.return_value = False

    async def _latest(user_id, kind):
        if kind == PartnerRequestKind.COURIER:
            return _request(status=PartnerRequestStatus.APPROVED)
        return _request(kind=PartnerRequestKind.BUSINESS, status=PartnerRequestStatus.CONTACTED)

    repos.partner.get_latest_for_user.side_effect = _latest
    access = run(pr_queries.PartnerRequestQuery().my_partner_access(info=_info(), jwt=_jwt()))
    assert access.courierApproved is True
    assert access.merchantApproved is False
    assert access.latestCourierRequest.status == PartnerRequestStatusEnum.APPROVED
    assert access.latestBusinessRequest.status == PartnerRequestStatusEnum.CONTACTED
    assert access.latestBusinessRequest.adminNotes is None


def test_my_partner_access_without_requests(repos):
    access = run(pr_queries.PartnerRequestQuery().my_partner_access(info=_info(), jwt=_jwt()))
    assert access.courierApproved is False
    assert access.merchantApproved is False
    assert access.latestCourierRequest is None
    assert access.latestBusinessRequest is None


def test_my_partner_access_merchant_approved(repos):
    repos.partner.exists_with_status.return_value = True
    access = run(pr_queries.PartnerRequestQuery().my_partner_access(info=_info(), jwt=_jwt()))
    assert access.merchantApproved is True
    repos.partner.exists_with_status.assert_awaited_with(
        USER_ID, PartnerRequestKind.BUSINESS, PartnerRequestStatus.APPROVED
    )


# ---------------------------------------------------------------- Panel Admin


@pytest.mark.parametrize("role", ["customer", "risk_admin"])
def test_admin_operations_reject_other_roles(repos, role):
    query = pr_queries.PartnerRequestQuery()
    mutation = pr_mutations.PartnerRequestMutation()
    with pytest.raises(Exception, match="Acceso denegado"):
        run(query.admin_partner_requests(info=_info(), jwt=_jwt(role)))
    with pytest.raises(Exception, match="Acceso denegado"):
        run(
            mutation.admin_update_partner_request(
                info=_info(), id=REQUEST_ID, status=PartnerRequestStatusEnum.APPROVED, jwt=_jwt(role)
            )
        )
    with pytest.raises(Exception, match="Autenticación requerida"):
        run(query.admin_partner_requests(info=_info(), jwt=""))
    repos.partner.list_requests.assert_not_awaited()
    repos.partner.update_status.assert_not_awaited()
    repos.couriers.approve_user.assert_not_awaited()


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_admin_list_with_filters(repos, role):
    repos.partner.list_requests.return_value = [_request()]
    repos.partner.count_requests.return_value = 7
    page = run(
        pr_queries.PartnerRequestQuery().admin_partner_requests(
            info=_info(),
            status=PartnerRequestStatusEnum.PENDING,
            type=PartnerRequestTypeEnum.COURIER,
            limit=500,
            offset=-3,
            jwt=_jwt(role, ADMIN_ID),
        )
    )
    assert page.total == 7
    assert page.items[0].adminNotes == "Llamar por la tarde"
    assert page.items[0].reviewedBy == ADMIN_ID
    repos.partner.list_requests.assert_awaited_once_with(
        status=PartnerRequestStatus.PENDING, kind=PartnerRequestKind.COURIER, limit=100, skip=0
    )
    repos.partner.count_requests.assert_awaited_once_with(
        status=PartnerRequestStatus.PENDING, kind=PartnerRequestKind.COURIER
    )


def _review(repos, current, new_status, notes=None, role="admin"):
    repos.partner.get_by_id.return_value = current
    repos.partner.update_status.return_value = _request(kind=current.type, status=new_status)
    return run(
        pr_mutations.PartnerRequestMutation().admin_update_partner_request(
            info=_info(), id=REQUEST_ID, status=PartnerRequestStatusEnum(new_status.value),
            adminNotes=notes, jwt=_jwt(role, ADMIN_ID),
        )
    )


def test_approving_courier_makes_user_an_approved_courier(repos):
    result = _review(repos, _request(), PartnerRequestStatus.APPROVED, notes="  Tiene moto ")
    repos.couriers.approve_user.assert_awaited_once_with(
        USER_ID, name="Ana Pérez", phone="+5355555555"
    )
    repos.approve_businesses.assert_not_awaited()
    repos.partner.update_status.assert_awaited_once_with(
        REQUEST_ID,
        PartnerRequestStatus.APPROVED,
        reviewed_by=ADMIN_ID,
        expected_status=PartnerRequestStatus.PENDING,
        admin_notes="Tiene moto",
        update_admin_notes=True,
    )
    assert result.status == PartnerRequestStatusEnum.APPROVED
    assert result.adminNotes == "Llamar por la tarde"


def test_approving_business_approves_pending_businesses(repos):
    _review(repos, _request(kind=PartnerRequestKind.BUSINESS, status=PartnerRequestStatus.CONTACTED), PartnerRequestStatus.APPROVED)
    repos.approve_businesses.assert_awaited_once_with(USER_ID)
    repos.couriers.approve_user.assert_not_awaited()


def test_contacted_only_changes_status(repos):
    _review(repos, _request(), PartnerRequestStatus.CONTACTED, role="manager")
    repos.couriers.approve_user.assert_not_awaited()
    repos.couriers.revoke_user.assert_not_awaited()
    kwargs = repos.partner.update_status.await_args.kwargs
    assert kwargs["update_admin_notes"] is False


def test_empty_admin_notes_clear_them(repos):
    _review(repos, _request(), PartnerRequestStatus.CONTACTED, notes="")
    kwargs = repos.partner.update_status.await_args.kwargs
    assert kwargs["update_admin_notes"] is True
    assert kwargs["admin_notes"] is None


def test_rejecting_pending_courier_gives_no_access(repos):
    _review(repos, _request(), PartnerRequestStatus.REJECTED)
    repos.couriers.approve_user.assert_not_awaited()
    repos.couriers.revoke_user.assert_not_awaited()


def test_rejecting_approved_courier_revokes_access(repos):
    _review(repos, _request(status=PartnerRequestStatus.APPROVED), PartnerRequestStatus.REJECTED)
    repos.couriers.revoke_user.assert_awaited_once_with(USER_ID)


def test_rejecting_approved_business_does_not_touch_couriers(repos):
    _review(
        repos,
        _request(kind=PartnerRequestKind.BUSINESS, status=PartnerRequestStatus.APPROVED),
        PartnerRequestStatus.REJECTED,
    )
    repos.couriers.revoke_user.assert_not_awaited()


@pytest.mark.parametrize("resolved", [PartnerRequestStatus.APPROVED, PartnerRequestStatus.REJECTED])
@pytest.mark.parametrize("reopen", [PartnerRequestStatus.PENDING, PartnerRequestStatus.CONTACTED])
def test_resolved_request_cannot_be_reopened(repos, resolved, reopen):
    with pytest.raises(Exception, match="no puede volver a pendiente"):
        _review(repos, _request(status=resolved), reopen)
    repos.partner.update_status.assert_not_awaited()


def test_concurrent_change_is_reported(repos):
    repos.partner.get_by_id.return_value = _request()
    repos.partner.update_status.return_value = None
    with pytest.raises(Exception, match="cambió mientras la revisabas"):
        run(
            pr_mutations.PartnerRequestMutation().admin_update_partner_request(
                info=_info(), id=REQUEST_ID, status=PartnerRequestStatusEnum.CONTACTED, jwt=_jwt("admin", ADMIN_ID)
            )
        )


def test_unknown_request(repos):
    with pytest.raises(Exception, match="Solicitud no encontrada"):
        run(
            pr_mutations.PartnerRequestMutation().admin_update_partner_request(
                info=_info(), id=REQUEST_ID, status=PartnerRequestStatusEnum.APPROVED, jwt=_jwt("admin", ADMIN_ID)
            )
        )


# ------------------------------------------------------------------ Mongo real


@pytest.fixture
def mongo_db(monkeypatch):
    """Base de datos temporal; se salta el test si no hay Mongo."""
    import clients.mongodb_client as mongodb_client
    from motor.motor_asyncio import AsyncIOMotorClient

    name = f"llego_test_partner_{uuid.uuid4().hex[:10]}"

    async def scenario(body):
        client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:
            client.close()
            pytest.skip("MongoDB no disponible en MONGODB_URL")
        db = client[name]
        monkeypatch.setattr(mongodb_client, "mongo_client", client)
        monkeypatch.setattr(mongodb_client, "database", db)
        try:
            await mongodb_client._create_partner_request_indexes()
            await db["delivery_persons"].create_index("userId", unique=True, name="idx_dp_user_id_unique")
            await body(db)
        finally:
            await client.drop_database(name)
            client.close()

    return lambda body: run(scenario(body))


def test_mongo_only_one_active_request_per_user_and_type(mongo_db):
    from repositories.partner_request_repository import PartnerRequestRepository

    repo = PartnerRequestRepository()
    base = {"userId": USER_ID, "fullName": "Ana", "phone": "+5355555555", "email": None,
            "businessName": None, "municipality": None, "notes": None}

    async def body(db):
        first = await repo.create({**base, "type": PartnerRequestKind.COURIER})
        # Otro tipo: permitido.
        await repo.create({**base, "type": PartnerRequestKind.BUSINESS})
        with pytest.raises(DuplicateKeyError):
            await repo.create({**base, "type": PartnerRequestKind.COURIER})

        # Contactada sigue activa; rechazada ya no bloquea una nueva.
        contacted = await repo.update_status(
            str(first.id), PartnerRequestStatus.CONTACTED, ADMIN_ID,
            expected_status=PartnerRequestStatus.PENDING,
        )
        assert contacted.active is True
        stale = await repo.update_status(
            str(first.id), PartnerRequestStatus.REJECTED, ADMIN_ID,
            expected_status=PartnerRequestStatus.PENDING,
        )
        assert stale is None  # otro admin la cambió: no se pisa
        rejected = await repo.update_status(
            str(first.id), PartnerRequestStatus.REJECTED, ADMIN_ID,
            expected_status=PartnerRequestStatus.CONTACTED, admin_notes="No contesta",
            update_admin_notes=True,
        )
        assert rejected.active is False
        assert rejected.adminNotes == "No contesta"
        assert str(rejected.reviewedBy) == ADMIN_ID
        assert rejected.reviewedAt.tzinfo is not None

        second = await repo.create({**base, "type": PartnerRequestKind.COURIER})
        latest = await repo.get_latest_for_user(USER_ID, PartnerRequestKind.COURIER)
        assert str(latest.id) == str(second.id)
        assert latest.createdAt.tzinfo is not None
        assert await repo.exists_with_status(USER_ID, PartnerRequestKind.COURIER, PartnerRequestStatus.REJECTED)
        assert not await repo.exists_with_status(USER_ID, PartnerRequestKind.BUSINESS, PartnerRequestStatus.APPROVED)
        assert await repo.count_requests(status=PartnerRequestStatus.PENDING) == 2
        assert await repo.count_requests(kind=PartnerRequestKind.COURIER) == 2
        assert len(await repo.list_requests(kind=PartnerRequestKind.BUSINESS)) == 1

    mongo_db(body)


def test_mongo_approve_user_creates_or_updates_the_courier_record(mongo_db):
    from bson import ObjectId

    from repositories.orders_repository import DeliveryPersonRepository
    from services.courier_access import is_approved_courier

    repo = DeliveryPersonRepository()
    legacy_user = "507f1f77bcf86cd799439031"

    async def body(db):
        # Sin registro: nace aprobado con el nombre y el teléfono de la solicitud.
        created = await repo.approve_user(USER_ID, name="Ana Pérez", phone="+5355555555")
        assert created.approved is True
        assert created.name == "Ana Pérez" and created.phone == "+5355555555"
        assert is_approved_courier(await repo.get_by_user_id(USER_ID))

        revoked = await repo.revoke_user(USER_ID)
        assert revoked.approved is False
        assert not is_approved_courier(await repo.get_by_user_id(USER_ID))
        assert await repo.revoke_user("507f1f77bcf86cd799439099") is None  # no crea

        # Registro legado (sin `approved`): cuenta como aprobado, y aprobarlo no
        # pisa sus datos.
        await db["delivery_persons"].insert_one({
            "_id": ObjectId(), "userId": ObjectId(legacy_user), "name": "Mensajero viejo",
            "phone": "+5352222222", "vehicleType": "bicicleta", "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        })
        legacy = await repo.get_by_user_id(legacy_user)
        assert legacy.approved is None and is_approved_courier(legacy)
        updated = await repo.approve_user(legacy_user, name="Otro nombre", phone="+5353333333")
        assert updated.approved is True
        assert updated.name == "Mensajero viejo" and updated.phone == "+5352222222"
        assert await db["delivery_persons"].count_documents({}) == 2

    mongo_db(body)
