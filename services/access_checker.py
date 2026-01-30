"""Access verification service for branches and businesses."""
from typing import Optional, Tuple
from datetime import datetime

from repositories import branches_repo, businesses_repo, business_access_repo


class AccessChecker:
    """Service to verify user access to branches and businesses."""

    async def check_branch_access(
        self,
        user_id: str,
        branch_id: str,
        require_owner: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a user has access to a branch.

        Args:
            user_id: User ID to check
            branch_id: Branch ID to check access for
            require_owner: If True, only owner access is allowed (for delete, change managers, etc.)

        Returns:
            Tuple of (has_access, error_message)
            - (True, None) if user has access
            - (False, "error message") if user does not have access
        """
        # Get branch
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            return False, "Sucursal no encontrada"

        # Get business
        business = await businesses_repo.get_by_id(branch.businessId)
        if not business:
            return False, "Negocio no encontrado"

        # Check if user is the business owner
        is_owner = business.ownerId == user_id

        # If require_owner, only owner can proceed
        if require_owner:
            if not is_owner:
                return False, "Solo el propietario del negocio puede realizar esta acción"
            return True, None

        # Check if user is owner
        if is_owner:
            return True, None

        # Check if user is a direct manager of the branch
        if user_id in branch.managerIds:
            # Verify access hasn't expired by checking BusinessAccess
            active_business_access = await business_access_repo.get_by_user_and_business(
                user_id,
                branch.businessId
            )

            # If user has business-level access, verify it's not expired
            if active_business_access:
                now = datetime.utcnow()
                if active_business_access.expiresAt and active_business_access.expiresAt <= now:
                    # Access has expired but worker hasn't run yet
                    return False, "Tu acceso a este negocio ha expirado"
                if not active_business_access.isActive:
                    # Access has been revoked
                    return False, "Tu acceso a este negocio ha sido revocado"

            # User is in managerIds and either has no expiring access or it's still valid
            return True, None

        # User has no access
        return False, "No autorizado para acceder a esta sucursal"

    async def check_business_access(
        self,
        user_id: str,
        business_id: str,
        require_owner: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a user has access to a business.

        Args:
            user_id: User ID to check
            business_id: Business ID to check access for
            require_owner: If True, only owner access is allowed

        Returns:
            Tuple of (has_access, error_message)
            - (True, None) if user has access
            - (False, "error message") if user does not have access
        """
        # Get business
        business = await businesses_repo.get_by_id(business_id)
        if not business:
            return False, "Negocio no encontrado"

        # Check if user is the business owner
        is_owner = business.ownerId == user_id

        # If require_owner, only owner can proceed
        if require_owner:
            if not is_owner:
                return False, "Solo el propietario del negocio puede realizar esta acción"
            return True, None

        # Check if user is owner
        if is_owner:
            return True, None

        # Check if user has business-level access
        active_business_access = await business_access_repo.get_by_user_and_business(
            user_id,
            business_id
        )

        if active_business_access:
            now = datetime.utcnow()

            # Check if access has expired
            if active_business_access.expiresAt and active_business_access.expiresAt <= now:
                return False, "Tu acceso a este negocio ha expirado"

            # Check if access is active
            if not active_business_access.isActive:
                return False, "Tu acceso a este negocio ha sido revocado"

            return True, None

        # User has no access
        return False, "No autorizado para acceder a este negocio"

    async def require_branch_access(
        self,
        user_id: str,
        branch_id: str,
        require_owner: bool = False
    ) -> None:
        """
        Require user to have access to a branch, raise exception if not.

        Args:
            user_id: User ID to check
            branch_id: Branch ID to check access for
            require_owner: If True, only owner access is allowed

        Raises:
            Exception: If user does not have access
        """
        has_access, error_message = await self.check_branch_access(
            user_id,
            branch_id,
            require_owner
        )
        if not has_access:
            raise Exception(error_message)

    async def require_business_access(
        self,
        user_id: str,
        business_id: str,
        require_owner: bool = False
    ) -> None:
        """
        Require user to have access to a business, raise exception if not.

        Args:
            user_id: User ID to check
            business_id: Business ID to check access for
            require_owner: If True, only owner access is allowed

        Raises:
            Exception: If user does not have access
        """
        has_access, error_message = await self.check_business_access(
            user_id,
            business_id,
            require_owner
        )
        if not has_access:
            raise Exception(error_message)


# Singleton instance
access_checker = AccessChecker()
