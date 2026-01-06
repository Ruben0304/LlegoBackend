"""GraphQL mutations for User entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import UserType
from .inputs import UpdateUserInput, AddBranchToUserInput, UpdateLocationInput
from repositories import users_repo, branches_repo, businesses_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file


@strawberry.type
class UserMutation:
    @strawberry.mutation(description="Actualizar perfil de usuario")
    async def update_user(
        self,
        info: Info,
        input: UpdateUserInput,
        jwt: Optional[str] = None
    ) -> UserType:
        """
        Update user profile. For avatar, upload first via POST /upload/user/avatar.
        Requires authentication.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Get current user
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.phone is not None:
            updates["phone"] = input.phone
        if input.avatar is not None:
            # Delete old avatar if exists
            if user.avatar:
                await delete_file(user.avatar)
            updates["avatar"] = input.avatar

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update user
        updated_user = await users_repo.update(user_id, updates)
        if not updated_user:
            raise Exception("Error al actualizar el usuario")

        return UserType(
            id=updated_user.id,
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail
        )

    @strawberry.mutation(description="Agregar sucursal a usuario")
    async def add_branch_to_user(
        self,
        info: Info,
        input: AddBranchToUserInput,
        jwt: Optional[str] = None
    ) -> UserType:
        """
        Add a branch to a user's branchIds list.
        Requires that the user has the business (that owns the branch) in their businessIds list.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Get current user
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Get the branch to verify it exists
        branch = await branches_repo.get_by_id(input.branchId)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Verify user owns the business that owns this branch
        if branch.businessId not in user.businessIds:
            raise Exception("No autorizado: el usuario no tiene acceso al negocio de esta sucursal")

        # Check if branch is already in user's branchIds
        if input.branchId in user.branchIds:
            raise Exception("La sucursal ya está asignada al usuario")

        # Add branch to user
        updated_user = await users_repo.add_branch_id(user_id, input.branchId)
        if not updated_user:
            raise Exception("Error al agregar la sucursal al usuario")

        return UserType(
            id=updated_user.id,
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail
        )

    @strawberry.mutation(description="Remover sucursal de usuario")
    async def remove_branch_from_user(
        self,
        info: Info,
        branch_id: str,
        jwt: Optional[str] = None
    ) -> UserType:
        """
        Remove a branch from a user's branchIds list.
        Only the user themselves can remove branches from their list.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Get current user
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Check if branch is in user's branchIds
        if branch_id not in user.branchIds:
            raise Exception("La sucursal no está asignada al usuario")

        # Remove branch from user
        updated_user = await users_repo.remove_branch_id(user_id, branch_id)
        if not updated_user:
            raise Exception("Error al remover la sucursal del usuario")

        return UserType(
            id=updated_user.id,
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail
        )

    @strawberry.mutation(description="Eliminar cuenta de usuario")
    async def delete_user(
        self,
        info: Info,
        jwt: Optional[str] = None
    ) -> bool:
        """
        Delete user account. Only the user themselves can delete their account.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Get current user
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Delete avatar if exists
        if user.avatar:
            await delete_file(user.avatar)

        # Delete user
        success = await users_repo.delete(user_id)
        if not success:
            raise Exception("Error al eliminar el usuario")

        return True


    @strawberry.mutation(description="Actualizar ubicación del usuario")
    async def update_location(
        self,
        info: Info,
        input: UpdateLocationInput,
        jwt: Optional[str] = None
    ) -> UserType:
        """
        Update user's current location.
        
        Args:
            input: Location coordinates (longitude, latitude)
            
        Note: Coordinates are stored as GeoJSON Point [longitude, latitude]
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Update location
        updated_user = await users_repo.update_location(
            user_id=user_id,
            longitude=input.longitude,
            latitude=input.latitude
        )
        
        if not updated_user:
            raise Exception("Error al actualizar la ubicación")

        return UserType(
            id=updated_user.id,
            name=updated_user.name,
            email=updated_user.email,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail
        )
