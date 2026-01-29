"""GraphQL mutations for Branch entity."""
import strawberry
from typing import Optional
from datetime import datetime
from strawberry.types import Info
from bson import ObjectId

from .types import BranchType, CoordinatesType, BranchTipo
from .inputs import CreateBranchInput, UpdateBranchInput
from .utils import branch_to_dict
from models import Branch, Coordinates
from repositories import branches_repo, businesses_repo, store_locations_repo, products_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file
from services.qdrant_indexing_service import qdrant_indexing_service


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

        # Validate paymentMethodIds is not empty
        if not input.paymentMethodIds:
            raise Exception("Debe especificar al menos un método de pago")

        # Verify payment methods exist
        from models import payment_methods_repo
        payment_methods = await payment_methods_repo.get_by_ids(input.paymentMethodIds)
        if len(payment_methods) != len(input.paymentMethodIds):
            raise Exception("Uno o más métodos de pago no existen")

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
            paymentMethodIds=input.paymentMethodIds,
            wallet={"local": 0.0, "usd": 0.0},
            walletStatus="active",
            createdAt=datetime.now()
        )

        # Step 1: Create in MongoDB first
        created_branch = await branches_repo.create(branch)

        # Step 2: Index in Qdrant with the MongoDB ID
        await qdrant_indexing_service.index_branch(created_branch)

        # Save location to MongoDB stores_location collection
        await store_locations_repo.upsert(
            store_id=branch_id,
            longitude=input.coordinates.lng,
            latitude=input.coordinates.lat,
            active=True
        )

        # Sync business-level access to the new branch
        from services.access_manager import access_manager
        await access_manager.sync_business_access_to_new_branch(created_branch.id)

        return BranchType(**branch_to_dict(created_branch))

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
        if input.paymentMethodIds is not None:
            if not input.paymentMethodIds:
                raise Exception("Debe especificar al menos un método de pago")
            # Verify payment methods exist
            from models import payment_methods_repo
            payment_methods = await payment_methods_repo.get_by_ids(input.paymentMethodIds)
            if len(payment_methods) != len(input.paymentMethodIds):
                raise Exception("Uno o más métodos de pago no existen")
            updates["paymentMethodIds"] = input.paymentMethodIds

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

        return BranchType(**branch_to_dict(updated_branch))

    @strawberry.mutation(description="Eliminar una sucursal")
    async def delete_branch(
        self,
        info: Info,
        branch_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """
        Delete a branch and all its associated data.
        Only the business owner can delete branches.
        This will also delete:
        - All products associated with the branch
        - The branch location from stores_location
        - Branch images from S3
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch exists
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Verify user is the business owner (only owner can delete, not managers)
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            raise Exception("Negocio no encontrado")

        if business.ownerId != user_id:
            raise Exception("Solo el propietario del negocio puede eliminar sucursales")

        # Delete branch images from S3
        if branch.avatar:
            await delete_file(branch.avatar)
        if branch.coverImage:
            await delete_file(branch.coverImage)

        # Delete all products associated with this branch
        products = await products_repo.get_by_branch(branch_id)
        for product in products:
            if product.image:
                await delete_file(product.image)
            await products_repo.delete(product.id)

        # Delete location from MongoDB stores_location
        await store_locations_repo.delete(branch_id)

        # Delete branch from Qdrant
        deleted = await branches_repo.delete(branch_id)
        if not deleted:
            raise Exception("Error al eliminar la sucursal")

        return True
