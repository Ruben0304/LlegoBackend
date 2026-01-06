"""GraphQL mutations for Branch entity."""
import strawberry
from typing import Optional
from datetime import datetime
from strawberry.types import Info
from bson import ObjectId

from .types import BranchType, CoordinatesType, BranchTipo
from .inputs import CreateBranchInput, UpdateBranchInput
from models import Branch, Coordinates
from repositories import branches_repo, businesses_repo, store_locations_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file


@strawberry.type
class BranchMutation:
    @strawberry.mutation(description="Crear una nueva sucursal")
    async def create_branch(
        self,
        info: Info,
        input: CreateBranchInput,
        jwt: Optional[str] = None
    ) -> BranchType:
        """
        Create a new branch. Upload images first via POST /upload/branch/avatar
        or POST /upload/branch/cover.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify business exists and user is owner
        business = await businesses_repo.get_by_id(input.businessId)
        if not business:
            raise Exception("Negocio no encontrado")

        if business.ownerId != user_id:
            raise Exception("No autorizado para crear sucursales en este negocio")

        # Validate tipos is not empty
        if not input.tipos:
            raise Exception("Debe especificar al menos un tipo de establecimiento")

        # Create branch
        branch_id = str(ObjectId())
        branch = Branch(
            id=branch_id,
            businessId=input.businessId,
            name=input.name,
            address=input.address,
            coordinates=Coordinates(
                type="Point",
                coordinates=[input.coordinates.lng, input.coordinates.lat]
            ),
            phone=input.phone,
            schedule=input.schedule,
            managerIds=input.managerIds or [user_id],
            status="active",
            avatar=input.avatar,
            coverImage=input.coverImage,
            deliveryRadius=input.deliveryRadius,
            facilities=input.facilities or [],
            tipos=[t.value for t in input.tipos],
            createdAt=datetime.now()
        )

        created_branch = await branches_repo.create(branch)

        # Save location to MongoDB stores_location collection
        await store_locations_repo.upsert(
            store_id=branch_id,
            longitude=input.coordinates.lng,
            latitude=input.coordinates.lat,
            active=True
        )

        return BranchType(
            id=created_branch.id,
            businessId=created_branch.businessId,
            name=created_branch.name,
            address=created_branch.address,
            coordinates=CoordinatesType(**created_branch.coordinates.model_dump()),
            phone=created_branch.phone,
            schedule=created_branch.schedule,
            managerIds=created_branch.managerIds,
            status=created_branch.status,
            avatar=created_branch.avatar,
            coverImage=created_branch.coverImage,
            deliveryRadius=created_branch.deliveryRadius,
            facilities=created_branch.facilities,
            tipos=[BranchTipo(t) for t in created_branch.tipos],
            createdAt=created_branch.createdAt
        )

    @strawberry.mutation(description="Actualizar una sucursal")
    async def update_branch(
        self,
        info: Info,
        branch_id: str,
        input: UpdateBranchInput,
        jwt: Optional[str] = None
    ) -> BranchType:
        """
        Update branch data. For new images, upload first via POST /upload/branch/avatar
        or POST /upload/branch/cover.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch exists
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Verify user has permission
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            raise Exception("Negocio no encontrado")

        if business.ownerId != user_id and user_id not in branch.managerIds:
            raise Exception("No autorizado para modificar esta sucursal")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.address is not None:
            updates["address"] = input.address
        if input.phone is not None:
            updates["phone"] = input.phone
        if input.schedule is not None:
            updates["schedule"] = input.schedule
        if input.status is not None:
            updates["status"] = input.status
        if input.deliveryRadius is not None:
            updates["deliveryRadius"] = input.deliveryRadius
        if input.facilities is not None:
            updates["facilities"] = input.facilities
        if input.managerIds is not None:
            # Only owner can change managers
            if business.ownerId != user_id:
                raise Exception("Solo el propietario puede modificar los managers")
            updates["managerIds"] = input.managerIds
        if input.avatar is not None:
            # Delete old avatar if exists
            if branch.avatar:
                await delete_file(branch.avatar)
            updates["avatar"] = input.avatar
        if input.coverImage is not None:
            # Delete old cover if exists
            if branch.coverImage:
                await delete_file(branch.coverImage)
            updates["coverImage"] = input.coverImage
        if input.tipos is not None:
            if not input.tipos:
                raise Exception("Debe especificar al menos un tipo de establecimiento")
            updates["tipos"] = [t.value for t in input.tipos]

        # Handle coordinates update - save to MongoDB stores_location
        if input.coordinates is not None:
            # Use upsert to create if not exists
            await store_locations_repo.upsert(
                store_id=branch_id,
                longitude=input.coordinates.lng,
                latitude=input.coordinates.lat,
                active=branch.status == "active"
            )
            # Also update in Qdrant metadata
            updates["coordinates"] = {
                "type": "Point",
                "coordinates": [input.coordinates.lng, input.coordinates.lat]
            }

        # Handle status change - sync active status to stores_location
        if input.status is not None:
            is_active = input.status == "active"
            await store_locations_repo.set_active(store_id=branch_id, active=is_active)

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update branch
        updated_branch = await branches_repo.update(branch_id, updates)
        if not updated_branch:
            raise Exception("Error al actualizar la sucursal")

        return BranchType(
            id=updated_branch.id,
            businessId=updated_branch.businessId,
            name=updated_branch.name,
            address=updated_branch.address,
            coordinates=CoordinatesType(**updated_branch.coordinates.model_dump()),
            phone=updated_branch.phone,
            schedule=updated_branch.schedule,
            managerIds=updated_branch.managerIds,
            status=updated_branch.status,
            avatar=updated_branch.avatar,
            coverImage=updated_branch.coverImage,
            deliveryRadius=updated_branch.deliveryRadius,
            facilities=updated_branch.facilities,
            tipos=[BranchTipo(t) for t in (updated_branch.tipos or [])],
            createdAt=updated_branch.createdAt
        )
