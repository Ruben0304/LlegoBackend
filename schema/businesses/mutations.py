from datetime import datetime
from typing import List, Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from domain.models import Branch, Business, Coordinates
from repositories import branches_repo, businesses_repo, users_repo
from schema.branches.transfer_accounts import (
    build_legacy_phones,
    build_legacy_qr_payments,
    normalize_transfer_accounts,
)
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file

from .inputs import (
    CreateBusinessInput,
    RegisterBranchInput,
    RegisterBusinessWithBranchesInput,
    UpdateBusinessInput,
)
from .types import BusinessType


@strawberry.type
class BusinessMutation:
    @strawberry.mutation(
        description="Registrar un nuevo negocio con al menos una sucursal"
    )
    async def register_business(
        self,
        info: Info,
        business_input: CreateBusinessInput,
        branches_input: List[RegisterBranchInput],
        jwt: Optional[str] = None,
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
            raise Exception(
                "Se requiere al menos una sucursal para registrar el negocio"
            )

        # 2. Crear Negocio
        business_id = ObjectId()

        business = Business(
            id=business_id,
            name=business_input.name,
            ownerId=user_id,
            globalRating=0.0,
            avatar=business_input.avatar or "",
            description=business_input.description,
            tags=business_input.tags or [],
            isActive=True,
            createdAt=datetime.now(),
        )

        # Step 1: Create business in MongoDB first
        created_business = await businesses_repo.create(business)

        # 2.1. Agregar businessId a la lista de businessIds del usuario
        await users_repo.add_business_id(user_id, business_id)

        # 3. Crear Sucursales
        for branch_inp in branches_input:
            # Validar que tipos no esté vacío
            if not branch_inp.tipos:
                raise Exception(
                    "Debe especificar al menos un tipo de establecimiento para cada sucursal"
                )

            # Validar que paymentMethodIds no esté vacío
            if not branch_inp.paymentMethodIds:
                raise Exception(
                    "Debe especificar al menos un método de pago para cada sucursal"
                )

            # Verificar que los métodos de pago existan
            from repositories import payment_methods_repo

            payment_methods = await payment_methods_repo.get_by_ids(
                branch_inp.paymentMethodIds
            )
            if len(payment_methods) != len(branch_inp.paymentMethodIds):
                raise Exception("Uno o más métodos de pago no existen")

            branch_id = ObjectId()
            normalized_accounts = normalize_transfer_accounts(branch_inp.accounts)

            branch = Branch(
                id=branch_id,
                businessId=business_id,
                name=branch_inp.name,
                address=branch_inp.address,
                coordinates=Coordinates(
                    type="Point",
                    coordinates=[
                        branch_inp.coordinates.lng,
                        branch_inp.coordinates.lat,
                    ],
                ),
                phone=branch_inp.phone,
                schedule=branch_inp.schedule,
                managerIds=branch_inp.managerIds or [user_id],
                isActive=True,
                avatar=branch_inp.avatar,
                coverImage=branch_inp.coverImage,
                socialMedia=branch_inp.socialMedia,
                tipos=[t.value for t in branch_inp.tipos],
                paymentMethodIds=branch_inp.paymentMethodIds,
                accounts=normalized_accounts,
                qrPayments=build_legacy_qr_payments(normalized_accounts),
                phones=build_legacy_phones(normalized_accounts),
                createdAt=datetime.now(),
            )

            # Create branch in MongoDB first
            created_branch = await branches_repo.create(branch)

        # 4. Retornar negocio creado
        return BusinessType(
            id=str(created_business.id),
            name=created_business.name,
            ownerId=str(created_business.ownerId),
            globalRating=created_business.globalRating,
            avatar=created_business.avatar,
            description=created_business.description,
            tags=created_business.tags,
            isActive=created_business.isActive,
            createdAt=created_business.createdAt,
        )

    @strawberry.mutation(description="Actualizar un negocio")
    async def update_business(
        self,
        info: Info,
        business_id: str,
        input: UpdateBusinessInput,
        jwt: Optional[str] = None,
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
        if str(business.ownerId) != user_id:
            raise Exception("No autorizado para modificar este negocio")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.description is not None:
            updates["description"] = input.description
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
            tags=updated_business.tags,
            isActive=updated_business.isActive,
            createdAt=updated_business.createdAt,
        )

    @strawberry.mutation(
        description="Registrar múltiples negocios con sus sucursales en una sola operación"
    )
    async def register_multiple_businesses(
        self,
        info: Info,
        businesses_input: List[RegisterBusinessWithBranchesInput],
        jwt: Optional[str] = None,
    ) -> List[BusinessType]:
        """
        Registra múltiples negocios con sus sucursales en una sola operación atómica.
        Si algún negocio falla, se hace rollback de todos los negocios creados.
        Requiere autenticación.
        """
        # 1. Autenticación
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        if not businesses_input:
            raise Exception("Se requiere al menos un negocio para registrar")

        # Validar que cada negocio tenga al menos una sucursal
        for idx, business_data in enumerate(businesses_input):
            if not business_data.branches:
                raise Exception(
                    f"El negocio en posición {idx} requiere al menos una sucursal"
                )

        created_businesses = []
        created_business_ids = []
        created_branch_ids = []

        try:
            # 2. Crear cada negocio con sus sucursales
            for business_data in businesses_input:
                business_input = business_data.business
                branches_input = business_data.branches

                # 2.1. Crear Negocio
                business_id = ObjectId()

                business = Business(
                    id=business_id,
                    name=business_input.name,
                    ownerId=user_id,
                    globalRating=0.0,
                    avatar=business_input.avatar or "",
                    description=business_input.description,
                    tags=business_input.tags or [],
                    isActive=True,
                    createdAt=datetime.now(),
                )

                # Create business in MongoDB first
                created_business = await businesses_repo.create(business)
                created_businesses.append(created_business)
                created_business_ids.append(business_id)

                # 2.2. Agregar businessId a la lista de businessIds del usuario
                await users_repo.add_business_id(user_id, business_id)

                # 2.3. Crear Sucursales
                for branch_inp in branches_input:
                    # Validar que tipos no esté vacío
                    if not branch_inp.tipos:
                        raise Exception(
                            f"Debe especificar al menos un tipo de establecimiento para cada sucursal del negocio '{business_input.name}'"
                        )

                    # Validar que paymentMethodIds no esté vacío
                    if not branch_inp.paymentMethodIds:
                        raise Exception(
                            f"Debe especificar al menos un método de pago para cada sucursal del negocio '{business_input.name}'"
                        )

                    # Verificar que los métodos de pago existan
                    from repositories import payment_methods_repo

                    payment_methods = await payment_methods_repo.get_by_ids(
                        branch_inp.paymentMethodIds
                    )
                    if len(payment_methods) != len(branch_inp.paymentMethodIds):
                        raise Exception(
                            f"Uno o más métodos de pago no existen para el negocio '{business_input.name}'"
                        )

                    branch_id = ObjectId()
                    normalized_accounts = normalize_transfer_accounts(branch_inp.accounts)

                    branch = Branch(
                        id=branch_id,
                        businessId=business_id,
                        name=branch_inp.name,
                        address=branch_inp.address,
                        coordinates=Coordinates(
                            type="Point",
                            coordinates=[
                                branch_inp.coordinates.lng,
                                branch_inp.coordinates.lat,
                            ],
                        ),
                        phone=branch_inp.phone,
                        schedule=branch_inp.schedule,
                        managerIds=branch_inp.managerIds or [user_id],
                        isActive=True,
                        avatar=branch_inp.avatar,
                        coverImage=branch_inp.coverImage,
                        socialMedia=branch_inp.socialMedia,
                        tipos=[t.value for t in branch_inp.tipos],
                        paymentMethodIds=branch_inp.paymentMethodIds,
                        accounts=normalized_accounts,
                        qrPayments=build_legacy_qr_payments(normalized_accounts),
                        phones=build_legacy_phones(normalized_accounts),
                        createdAt=datetime.now(),
                    )

                    # Create branch in MongoDB first
                    created_branch = await branches_repo.create(branch)
                    created_branch_ids.append(branch_id)

            # 3. Retornar negocios creados
            return [
                BusinessType(
                    id=str(b.id),
                    name=b.name,
                    ownerId=str(b.ownerId),
                    globalRating=b.globalRating,
                    avatar=b.avatar,
                    description=b.description,
                    tags=b.tags,
                    isActive=b.isActive,
                    createdAt=b.createdAt,
                )
                for b in created_businesses
            ]

        except Exception as e:
            # Rollback: eliminar todos los negocios y sucursales creados
            for business_id in created_business_ids:
                try:
                    await businesses_repo.delete(business_id)
                    await users_repo.remove_business_id(user_id, business_id)
                except Exception:
                    pass  # Ignorar errores en rollback

            for branch_id in created_branch_ids:
                try:
                    await branches_repo.delete(branch_id)
                except Exception:
                    pass  # Ignorar errores en rollback

            # Re-lanzar la excepción original
            raise Exception(f"Error al registrar múltiples negocios: {str(e)}")

    @strawberry.mutation(description="Eliminar un negocio y todas sus sucursales")
    async def delete_business(
        self,
        info: Info,
        business_id: str,
        jwt: Optional[str] = None,
    ) -> bool:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise Exception("Negocio no encontrado")

        # Convert user_id to ObjectId for comparison with business.ownerId
        if str(business.ownerId) != user_id:
            raise Exception("No autorizado para eliminar este negocio")

        # Delete all branches of this business
        branches = await branches_repo.get_by_business(business_id)
        for branch in branches:
            await branches_repo.delete(branch.id)

        # Delete business
        deleted = await businesses_repo.delete(business_id)
        if not deleted:
            raise Exception("Error al eliminar el negocio")

        # Remove businessId from user
        await users_repo.remove_business_id(user_id, business_id)

        return True
