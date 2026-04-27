"""GraphQL mutations for User entity."""
import uuid
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import UserType, SavedAddressType
from schema.wallet.types import WalletBalanceType
from .inputs import (
    UpdateUserInput,
    AddBranchToUserInput,
    UpdateLocationInput,
    SavedAddressInput,
    UpdateSavedAddressInput,
)
from repositories import users_repo, branches_repo, businesses_repo
from utils.graphql_auth import apply_optional_jwt, require_role
from utils.s3 import delete_file


def _user_to_type(u) -> UserType:
    """Convert a User domain model to UserType GraphQL type."""
    return UserType(
        id=u.id,
        name=u.name,
        email=u.email,
        username=u.username,
        phone=u.phone,
        role=u.role,
        avatar=u.avatar,
        businessIds=u.businessIds,
        branchIds=u.branchIds,
        businessAccessIds=getattr(u, 'businessAccessIds', []),
        createdAt=u.createdAt,
        authProvider=u.authProvider,
        providerUserId=u.providerUserId,
        applePrivateEmail=u.applePrivateEmail,
        wallet=WalletBalanceType(
            local=u.wallet.get('local', 0.0),
            usd=u.wallet.get('usd', 0.0),
        ),
        walletStatus=u.walletStatus,
        isPro=getattr(u, 'isPro', False),
        location=getattr(u, 'location', None),
        aiConsultasLimit=getattr(u, 'aiConsultasLimit', None),
        savedAddresses=[
            SavedAddressType(
                id=a.id,
                label=a.label,
                street=a.street,
                city=a.city,
                reference=a.reference,
                addressType=a.addressType,
                buildingName=a.buildingName,
                floor=a.floor,
                apartment=a.apartment,
                deliveryInstructions=a.deliveryInstructions,
                latitude=a.latitude,
                longitude=a.longitude,
            )
            for a in getattr(u, 'savedAddresses', [])
        ],
        defaultAddressId=getattr(u, 'defaultAddressId', None),
    )


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
        if input.username is not None:
            # Validate username is unique
            if await users_repo.username_exists(input.username, exclude_user_id=user_id):
                raise Exception(f"El nombre de usuario '{input.username}' ya está en uso")
            updates["username"] = input.username
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
            username=updated_user.username,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail,
            wallet=WalletBalanceType(local=updated_user.wallet.get('local', 0.0), usd=updated_user.wallet.get('usd', 0.0)),
            walletStatus=updated_user.walletStatus
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
            username=updated_user.username,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail,
            wallet=WalletBalanceType(local=updated_user.wallet.get('local', 0.0), usd=updated_user.wallet.get('usd', 0.0)),
            walletStatus=updated_user.walletStatus
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
            username=updated_user.username,
            phone=updated_user.phone,
            role=updated_user.role,
            avatar=updated_user.avatar,
            businessIds=updated_user.businessIds,
            branchIds=updated_user.branchIds,
            createdAt=updated_user.createdAt,
            authProvider=updated_user.authProvider,
            providerUserId=updated_user.providerUserId,
            applePrivateEmail=updated_user.applePrivateEmail,
            wallet=WalletBalanceType(local=updated_user.wallet.get('local', 0.0), usd=updated_user.wallet.get('usd', 0.0)),
            walletStatus=updated_user.walletStatus
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

        return _user_to_type(updated_user)

    # ------------------------------------------------------------------
    # Saved Addresses
    # ------------------------------------------------------------------

    @strawberry.mutation(description="Guardar una nueva dirección de entrega en el perfil")
    async def add_saved_address(
        self,
        info: Info,
        input: SavedAddressInput,
        jwt: Optional[str] = None,
    ) -> UserType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        address_id = str(uuid.uuid4())
        address_dict = {
            "id": address_id,
            "label": input.label,
            "street": input.street,
            "latitude": input.latitude,
            "longitude": input.longitude,
            "city": input.city,
            "reference": input.reference,
            "addressType": input.addressType,
            "buildingName": input.buildingName,
            "floor": input.floor,
            "apartment": input.apartment,
            "deliveryInstructions": input.deliveryInstructions,
        }

        updated_user = await users_repo.add_saved_address(user_id, address_dict)
        if not updated_user:
            raise Exception("Error al guardar la dirección")

        if input.setAsDefault:
            updated_user = await users_repo.set_default_address(user_id, address_id)

        return _user_to_type(updated_user)

    @strawberry.mutation(description="Editar una dirección guardada en el perfil")
    async def update_saved_address(
        self,
        info: Info,
        input: UpdateSavedAddressInput,
        jwt: Optional[str] = None,
    ) -> UserType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Find the existing address to merge with
        existing = next(
            (a for a in user.savedAddresses if a.id == input.addressId), None
        )
        if not existing:
            raise Exception("Dirección no encontrada")

        # Merge: only update provided fields
        updated_dict = {
            "id": existing.id,
            "label": input.label if input.label is not None else existing.label,
            "street": input.street if input.street is not None else existing.street,
            "latitude": input.latitude if input.latitude is not None else existing.latitude,
            "longitude": input.longitude if input.longitude is not None else existing.longitude,
            "city": input.city if input.city is not None else existing.city,
            "reference": input.reference if input.reference is not None else existing.reference,
            "addressType": input.addressType if input.addressType is not None else existing.addressType,
            "buildingName": input.buildingName if input.buildingName is not None else existing.buildingName,
            "floor": input.floor if input.floor is not None else existing.floor,
            "apartment": input.apartment if input.apartment is not None else existing.apartment,
            "deliveryInstructions": input.deliveryInstructions if input.deliveryInstructions is not None else existing.deliveryInstructions,
        }

        updated_user = await users_repo.update_saved_address(user_id, input.addressId, updated_dict)
        if not updated_user:
            raise Exception("Error al actualizar la dirección")

        if input.setAsDefault is True:
            updated_user = await users_repo.set_default_address(user_id, input.addressId)

        return _user_to_type(updated_user)

    @strawberry.mutation(description="Eliminar una dirección guardada del perfil")
    async def remove_saved_address(
        self,
        info: Info,
        addressId: str,
        jwt: Optional[str] = None,
    ) -> UserType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        updated_user = await users_repo.remove_saved_address(user_id, addressId)
        if not updated_user:
            raise Exception("Error al eliminar la dirección")

        # If deleted address was the default, clear defaultAddressId
        if updated_user.defaultAddressId == addressId:
            updated_user = await users_repo.set_default_address(user_id, None)

        return _user_to_type(updated_user)

    @strawberry.mutation(description="Establecer la dirección de entrega por defecto")
    async def set_default_address(
        self,
        info: Info,
        addressId: str,
        jwt: Optional[str] = None,
    ) -> UserType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        # Verify the address belongs to the user
        if not any(a.id == addressId for a in user.savedAddresses):
            raise Exception("Dirección no encontrada en el perfil")

        updated_user = await users_repo.set_default_address(user_id, addressId)
        if not updated_user:
            raise Exception("Error al actualizar la dirección por defecto")

        return _user_to_type(updated_user)

    @strawberry.mutation(description="Cambiar estado de wallet de un usuario (admin/manager)")
    async def admin_set_user_wallet_status(
        self,
        info: Info,
        user_id: str,
        status: str,
        jwt: str,
    ) -> UserType:
        """
        Set a user's walletStatus. Valid values: 'active', 'frozen', 'closed'.
        'frozen' effectively bans the user from transacting. Requires admin or manager role.
        """
        require_role(jwt, info, ["admin", "manager"])
        valid_statuses = {"active", "frozen", "closed"}
        if status not in valid_statuses:
            raise Exception(f"Estado inválido. Debe ser uno de: {', '.join(valid_statuses)}")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        updated_user = await users_repo.update(user_id, {"walletStatus": status})
        if not updated_user:
            raise Exception("Error al actualizar el estado del usuario")

        return _user_to_type(updated_user)
