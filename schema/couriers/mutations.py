"""GraphQL mutations for courier verification."""

from typing import List, Optional

import strawberry
from pymongo.errors import DuplicateKeyError
from strawberry.types import Info

from domain.orders import CourierVerificationStatus
from repositories import branches_repo
from repositories.orders_repository import delivery_persons_repo
from services.courier_verification import (
    normalize_courier_profile,
    normalize_rejection_reason,
)
from utils.graphql_auth import require_auth, require_role

from .queries import ADMIN_ROLES
from .types import CourierProfileType, courier_to_type


@strawberry.input
class SubmitCourierProfileInput:
    firstName: str
    lastName: str
    identityCard: str


@strawberry.input
class ReviewCourierInput:
    courierId: str
    approve: bool
    rejectionReason: Optional[str] = None
    # Al aprobar, sustituye las sucursales asignadas si se envía.
    branchIds: Optional[List[str]] = None


async def _validated_branch_ids(branch_ids: List[str]) -> List[str]:
    unique_ids = list(dict.fromkeys(branch_ids))
    found = await branches_repo.get_by_ids(unique_ids)
    found_ids = {str(b.id) for b in found}
    missing = [b for b in unique_ids if b not in found_ids]
    if missing:
        raise Exception(f"Sucursal no encontrada: {', '.join(missing)}")
    return unique_ids


@strawberry.type
class CourierMutation:
    @strawberry.mutation(
        description="El mensajero envía nombre, apellido y carnet; queda en verificación"
    )
    async def submit_courier_profile(
        self, info: Info, input: SubmitCourierProfileInput, jwt: str
    ) -> CourierProfileType:
        from schema.orders.queries import _get_or_create_delivery_person

        user_id = require_auth(jwt, info)
        delivery_person = await _get_or_create_delivery_person(user_id)

        if delivery_person.is_approved:
            raise Exception("Tu cuenta ya está verificada")

        try:
            first_name, last_name, identity_card = normalize_courier_profile(
                input.firstName, input.lastName, input.identityCard
            )
        except ValueError as e:
            raise Exception(str(e))

        owner = await delivery_persons_repo.get_by_identity_card(identity_card)
        if owner and str(owner.id) != str(delivery_person.id):
            raise Exception("Este carnet ya está registrado en otra cuenta")

        try:
            updated = await delivery_persons_repo.submit_verification(
                str(delivery_person.id), first_name, last_name, identity_card
            )
        except DuplicateKeyError:
            raise Exception("Este carnet ya está registrado en otra cuenta")
        if not updated:
            raise Exception("Tu cuenta ya está verificada")
        return await courier_to_type(updated)

    @strawberry.mutation(description="(Admin) Aprobar o rechazar un mensajero")
    async def review_courier(
        self, info: Info, input: ReviewCourierInput, jwt: str
    ) -> CourierProfileType:
        reviewer_id = require_role(jwt, info, ADMIN_ROLES)

        dp = await delivery_persons_repo.get_by_id(input.courierId)
        if not dp:
            raise Exception("Mensajero no encontrado")
        if dp.verificationStatus == CourierVerificationStatus.INCOMPLETE:
            raise Exception("El mensajero aún no ha enviado sus datos")

        if input.approve:
            if input.branchIds is not None:
                branch_ids = await _validated_branch_ids(input.branchIds)
                await delivery_persons_repo.set_linked_branches(str(dp.id), branch_ids)
            updated = await delivery_persons_repo.review_verification(
                str(dp.id), CourierVerificationStatus.APPROVED, reviewer_id
            )
        else:
            try:
                reason = normalize_rejection_reason(input.rejectionReason or "")
            except ValueError as e:
                raise Exception(str(e))
            updated = await delivery_persons_repo.review_verification(
                str(dp.id), CourierVerificationStatus.REJECTED, reviewer_id, reason
            )

        if not updated:
            raise Exception("Mensajero no encontrado")
        return await courier_to_type(updated)

    @strawberry.mutation(
        description="(Admin) Definir las sucursales cuyos pedidos verá un mensajero"
    )
    async def set_courier_branches(
        self, info: Info, courierId: str, branchIds: List[str], jwt: str
    ) -> CourierProfileType:
        require_role(jwt, info, ADMIN_ROLES)

        branch_ids = await _validated_branch_ids(branchIds)
        updated = await delivery_persons_repo.set_linked_branches(courierId, branch_ids)
        if not updated:
            raise Exception("Mensajero no encontrado")
        return await courier_to_type(updated)
