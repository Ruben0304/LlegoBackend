"""GraphQL mutations for FavoritesCart entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import FavoriteCartType
from repositories import favorites_cart_repo
from utils.graphql_auth import require_auth


@strawberry.type
class FavoritesCartMutation:
    @strawberry.mutation(description="Agregar producto a favoritos")
    async def add_favorite(
        self,
        info: Info,
        product_id: str,
        jwt: Optional[str] = None
    ) -> Optional[FavoriteCartType]:
        """
        Add a product to user's favorites.
        Returns None if already exists.
        """
        user_id = require_auth(jwt, info)

        result = await favorites_cart_repo.add(user_id, product_id, "favorite")

        if not result:
            raise Exception("El producto ya está en favoritos")

        return FavoriteCartType(
            id=result.id,
            userId=result.userId,
            productId=result.productId,
            type=result.type,
            createdAt=result.createdAt
        )

    @strawberry.mutation(description="Agregar producto al carrito")
    async def add_to_cart(
        self,
        info: Info,
        product_id: str,
        jwt: Optional[str] = None
    ) -> Optional[FavoriteCartType]:
        """
        Add a product to user's cart.
        Returns None if already exists.
        """
        user_id = require_auth(jwt, info)

        result = await favorites_cart_repo.add(user_id, product_id, "cart")

        if not result:
            raise Exception("El producto ya está en el carrito")

        return FavoriteCartType(
            id=result.id,
            userId=result.userId,
            productId=result.productId,
            type=result.type,
            createdAt=result.createdAt
        )

    @strawberry.mutation(description="Remover producto de favoritos")
    async def remove_favorite(
        self,
        info: Info,
        product_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """Remove a product from user's favorites."""
        user_id = require_auth(jwt, info)

        success = await favorites_cart_repo.remove(user_id, product_id, "favorite")

        if not success:
            raise Exception("El producto no está en favoritos")

        return True

    @strawberry.mutation(description="Remover producto del carrito")
    async def remove_from_cart(
        self,
        info: Info,
        product_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """Remove a product from user's cart."""
        user_id = require_auth(jwt, info)

        success = await favorites_cart_repo.remove(user_id, product_id, "cart")

        if not success:
            raise Exception("El producto no está en el carrito")

        return True
