import strawberry
from typing import List, Optional
from datetime import datetime
from strawberry.types import Info
from bson import ObjectId

from models import Business, Branch, Coordinates
from repositories import businesses_repo, branches_repo, users_repo
from .inputs import CreateBusinessInput, RegisterBranchInput, UpdateBusinessInput
from .types import BusinessType
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file


@strawberry.type
class BusinessMutation:
    @strawberry.mutation(description="Registrar un nuevo negocio con al menos una sucursal")
    async def register_business(
        self,
        info: Info,
        business_input: CreateBusinessInput,
        branches_input: List[RegisterBranchInput],
        jwt: Optional[str] = None
    ) -> BusinessType:
        """
        Registra un negocio y sus sucursales iniciales.
        Para avatar/cover images, usar POST /businesses/{id}/avatar o /cover endpoints.
        Requiere autenticación.
        """
        # 1. Autenticación
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        if not branches_input:
            raise Exception("Se requiere al menos una sucursal para registrar el negocio")

        # 2. Crear Negocio
        business_id = str(ObjectId())

        business = Business(
            id=business_id,
            name=business_input.name,
            ownerId=user_id,
            globalRating=0.0,
            avatar=business_input.avatar or "",
            description=business_input.description,
            socialMedia=business_input.socialMedia,
            tags=business_input.tags or [],
            isActive=True,
            createdAt=datetime.now()
        )

        created_business = await businesses_repo.create(business)

        # 2.1. Agregar businessId a la lista de businessIds del usuario
        await users_repo.add_business_id(user_id, business_id)

        # 3. Crear Sucursales
        for branch_inp in branches_input:
            # Validar que tipos no esté vacío
            if not branch_inp.tipos:
                raise Exception("Debe especificar al menos un tipo de establecimiento para cada sucursal")
            
            # Validar que paymentMethodIds no esté vacío
            if not branch_inp.paymentMethodIds:
                raise Exception("Debe especificar al menos un método de pago para cada sucursal")
            
            # Verificar que los métodos de pago existan
            from models import payment_methods_repo
            payment_methods = await payment_methods_repo.get_by_ids(branch_inp.paymentMethodIds)
            if len(payment_methods) != len(branch_inp.paymentMethodIds):
                raise Exception("Uno o más métodos de pago no existen")
            
            branch_id = str(ObjectId())

            branch = Branch(
                id=branch_id,
                businessId=business_id,
                name=branch_inp.name,
                address=branch_inp.address,
                coordinates=Coordinates(
                    type="Point",
                    coordinates=[branch_inp.coordinates.lng, branch_inp.coordinates.lat]
                ),
                phone=branch_inp.phone,
                schedule=branch_inp.schedule,
                managerIds=branch_inp.managerIds or [user_id],
                status="active",
                avatar=branch_inp.avatar,
                coverImage=branch_inp.coverImage,
                deliveryRadius=branch_inp.deliveryRadius,
                facilities=branch_inp.facilities or [],
                tipos=[t.value for t in branch_inp.tipos],
                paymentMethodIds=branch_inp.paymentMethodIds,
                createdAt=datetime.now()
            )

            await branches_repo.create(branch)

        # 4. Retornar negocio creado
        return BusinessType(
            id=created_business.id,
            name=created_business.name,
            ownerId=created_business.ownerId,
            globalRating=created_business.globalRating,
            avatar=created_business.avatar,
            description=created_business.description,
            socialMedia=created_business.socialMedia,
            tags=created_business.tags,
            isActive=created_business.isActive,
            createdAt=created_business.createdAt
        )

    @strawberry.mutation(description="Actualizar un negocio")
    async def update_business(
        self,
        info: Info,
        business_id: str,
        input: UpdateBusinessInput,
        jwt: Optional[str] = None
    ) -> BusinessType:
        """
        Actualiza datos de un negocio. Para imágenes, subirlas primero via
        POST /upload/business/avatar endpoint.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify business exists
        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise Exception("Negocio no encontrado")

        # Verify user is owner
        if business.ownerId != user_id:
            raise Exception("No autorizado para modificar este negocio")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.description is not None:
            updates["description"] = input.description
        if input.socialMedia is not None:
            updates["socialMedia"] = input.socialMedia
        if input.tags is not None:
            updates["tags"] = input.tags
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.avatar is not None:
            # Delete old avatar if exists
            if business.avatar:
                await delete_file(business.avatar)
            updates["avatar"] = input.avatar

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update business
        updated_business = await businesses_repo.update(business_id, updates)
        if not updated_business:
            raise Exception("Error al actualizar el negocio")

        return BusinessType(
            id=updated_business.id,
            name=updated_business.name,
            ownerId=updated_business.ownerId,
            globalRating=updated_business.globalRating,
            avatar=updated_business.avatar,
            description=updated_business.description,
            socialMedia=updated_business.socialMedia,
            tags=updated_business.tags,
            isActive=updated_business.isActive,
            createdAt=updated_business.createdAt
        )
