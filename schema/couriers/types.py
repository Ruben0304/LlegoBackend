"""GraphQL types for courier verification (app de mensajeros + Panel Admin)."""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import strawberry

from domain.orders import DeliveryPerson
from repositories import branches_repo, businesses_repo, users_repo


@strawberry.enum
class CourierVerificationStatusEnum(Enum):
    INCOMPLETE = "incomplete"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@strawberry.type
class CourierBranchType:
    id: str
    name: str
    address: Optional[str]
    businessId: str
    businessName: Optional[str]


@strawberry.type
class CourierProfileType:
    id: str
    userId: str
    name: str
    firstName: Optional[str]
    lastName: Optional[str]
    identityCard: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    avatar: Optional[str]
    verificationStatus: CourierVerificationStatusEnum
    rejectionReason: Optional[str]
    submittedAt: Optional[datetime]
    reviewedAt: Optional[datetime]
    createdAt: datetime
    rating: float
    totalDeliveries: int
    branches: List[CourierBranchType]


@strawberry.type
class CouriersConnectionType:
    rows: List[CourierProfileType]
    totalCount: int
    hasMore: bool


async def branches_to_types(branch_ids: List[str]) -> Dict[str, CourierBranchType]:
    """Sucursales (con nombre del negocio) indexadas por id, en dos consultas."""
    branches = await branches_repo.get_by_ids([str(b) for b in branch_ids])
    business_ids = list({str(b.businessId) for b in branches})
    businesses = await businesses_repo.get_by_ids(business_ids) if business_ids else []
    business_names = {str(b.id): b.name for b in businesses}
    return {
        str(b.id): CourierBranchType(
            id=str(b.id),
            name=b.name,
            address=b.address,
            businessId=str(b.businessId),
            businessName=business_names.get(str(b.businessId)),
        )
        for b in branches
    }


async def couriers_to_types(couriers: List[DeliveryPerson]) -> List[CourierProfileType]:
    all_branch_ids = {str(b) for dp in couriers for b in dp.linkedBranchIds}
    branch_types = await branches_to_types(list(all_branch_ids))
    users = await asyncio.gather(
        *(users_repo.get_by_id(str(dp.userId)) for dp in couriers)
    )
    result = []
    for dp, user in zip(couriers, users):
        result.append(
            CourierProfileType(
                id=str(dp.id),
                userId=str(dp.userId),
                name=dp.name,
                firstName=dp.firstName,
                lastName=dp.lastName,
                identityCard=dp.identityCard,
                phone=dp.phone or (user.phone if user else None),
                email=user.email if user else None,
                avatar=(user.avatar if user else None) or dp.profileImageUrl,
                verificationStatus=CourierVerificationStatusEnum(
                    dp.verificationStatus.value
                ),
                rejectionReason=dp.verificationRejectionReason,
                submittedAt=dp.verificationSubmittedAt,
                reviewedAt=dp.verificationReviewedAt,
                createdAt=dp.createdAt,
                rating=dp.rating,
                totalDeliveries=dp.totalDeliveries,
                branches=[
                    branch_types[str(b)]
                    for b in dp.linkedBranchIds
                    if str(b) in branch_types
                ],
            )
        )
    return result


async def courier_to_type(dp: DeliveryPerson) -> CourierProfileType:
    return (await couriers_to_types([dp]))[0]
