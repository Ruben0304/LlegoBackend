"""GraphQL query resolvers for synchronization."""

from datetime import datetime
from typing import List, Optional, Set, Tuple

import strawberry
from strawberry.types import Info

from repositories import branches_repo, businesses_repo, products_repo
from schema.branches.utils import schedule_to_type
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import get_image_variant_path, get_public_url

from .types import (
    BusinessSyncType,
    BranchSyncType,
    CoordinatesSyncType,
    ImageQuality,
    ImageSyncType,
    ImageUrlType,
    ProductSyncType,
    SyncCheckpoint,
)


def _effective_updated_at(entity) -> datetime:
    """updatedAt si existe (se setea en cada update()), si no createdAt."""
    ts = entity.updatedAt or entity.createdAt
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


def _changed_since(entity, since: Optional[datetime]) -> bool:
    """True si `entity` es nuevo o se modificó después de `since` (o si since es None)."""
    if since is None:
        return True
    naive_since = since.replace(tzinfo=None) if since.tzinfo is not None else since
    return _effective_updated_at(entity) > naive_since


async def _get_active_business_and_branch_ids() -> Tuple[Set[str], Set[str]]:
    """IDs de negocios activos y de sucursales activas cuyo negocio también está activo.

    Se usa para que sync_products/sync_images no expongan catálogo de negocios
    pendientes de aprobación o rechazados (mismo criterio que sync_businesses_with_branches).
    """
    active_business_ids: Set[str] = set()
    active_branch_ids: Set[str] = set()

    all_businesses = await businesses_repo.get_all()
    for business in all_businesses:
        if not business.isActive:
            continue
        active_business_ids.add(str(business.id))

        branches = await branches_repo.get_by_business(str(business.id))
        for branch in branches:
            if branch.isActive:
                active_branch_ids.add(str(branch.id))

    return active_business_ids, active_branch_ids


async def _get_active_product_ids(active_branch_ids: Set[str]) -> Set[str]:
    """IDs de productos cuya sucursal está en active_branch_ids."""
    all_products = await products_repo.get_all()
    return {
        str(product.id)
        for product in all_products
        if str(product.branchId) in active_branch_ids
    }


@strawberry.type
class SyncQuery:
    @strawberry.field(
        description=(
            "Checkpoint de sincronización: IDs actualmente activos (para que el "
            "cliente borre localmente lo que ya no está) y marca de tiempo del "
            "servidor a guardar como `since` para el próximo sync incremental."
        )
    )
    async def sync_checkpoint(
        self, info: Info, jwt: Optional[str] = None
    ) -> SyncCheckpoint:
        apply_optional_jwt(jwt, info)

        # Capturado antes de leer, para no perder cambios concurrentes (peor caso:
        # se recogen de nuevo en el próximo sync incremental, nunca se pierden).
        synced_at = datetime.now()

        active_business_ids, active_branch_ids = (
            await _get_active_business_and_branch_ids()
        )
        active_product_ids = await _get_active_product_ids(active_branch_ids)

        return SyncCheckpoint(
            businessIds=sorted(active_business_ids),
            branchIds=sorted(active_branch_ids),
            productIds=sorted(active_product_ids),
            syncedAt=synced_at,
        )

    @strawberry.field(
        description="Sincronizar negocios con sus branches (excluye datos sensibles como managerIds y ownerId)"
    )
    async def sync_businesses_with_branches(
        self, info: Info, since: Optional[datetime] = None, jwt: Optional[str] = None
    ) -> List[BusinessSyncType]:
        """
        Get all businesses with their branches for local synchronization.

        This query excludes sensitive data such as:
        - ownerId
        - managerIds
        - Payment account details
        - Wallet information

        Suitable for public/offline caching.

        Args:
            since: si se indica, solo se devuelven negocios (con sus sucursales
                nuevas/modificadas) que cambiaron después de esta fecha. Úsalo
                junto con syncCheckpoint para sync incremental; omítelo para
                traer el catálogo completo.
        """
        apply_optional_jwt(jwt, info)

        # Get all active businesses
        all_businesses = await businesses_repo.get_all()

        # Get all branches grouped by business
        result = []
        for business in all_businesses:
            if not business.isActive:
                continue

            # Get branches for this business
            branches = await branches_repo.get_by_business(str(business.id))

            # Convert branches to sync type (excluding sensitive data).
            # Solo se incluyen las sucursales nuevas/modificadas desde `since`
            # (todas si since es None); el negocio se incluye si él mismo cambió
            # o si tiene al menos una sucursal cambiada.
            branch_sync_list = []
            for branch in branches:
                if not branch.isActive or not _changed_since(branch, since):
                    continue

                branch_sync = BranchSyncType(
                    id=str(branch.id),
                    businessId=str(branch.businessId),
                    name=branch.name,
                    address=branch.address,
                    coordinates=CoordinatesSyncType(
                        type=branch.coordinates.type,
                        coordinates=branch.coordinates.coordinates,
                    ),
                    phone=branch.phone,
                    schedule=schedule_to_type(branch.schedule),
                    isActive=branch.isActive,
                    status=branch.status,
                    avatar=branch.avatar,
                    coverImage=branch.coverImage,
                    socialMedia=branch.socialMedia,
                    tipos=branch.tipos,
                    useAppMessaging=branch.useAppMessaging,
                    vehicles=branch.vehicles,
                    deliveryRadius=branch.deliveryRadius,
                    acceptedCurrency=branch.acceptedCurrency,
                    exchangeRate=branch.exchangeRate,
                    createdAt=branch.createdAt,
                )
                branch_sync_list.append(branch_sync)

            # Nada que enviar de este negocio en este sync incremental
            if not branch_sync_list and not _changed_since(business, since):
                continue

            # Create business sync type
            business_sync = BusinessSyncType(
                id=str(business.id),
                name=business.name,
                globalRating=business.globalRating,
                avatar=business.avatar,
                description=business.description,
                tags=business.tags,
                isActive=business.isActive,
                createdAt=business.createdAt,
                branches=branch_sync_list,
            )
            result.append(business_sync)

        return result

    @strawberry.field(
        description="Sincronizar productos (todos los productos disponibles)"
    )
    async def sync_products(
        self,
        info: Info,
        branch_id: Optional[str] = None,
        category_id: Optional[str] = None,
        available_only: bool = False,
        since: Optional[datetime] = None,
        jwt: Optional[str] = None,
    ) -> List[ProductSyncType]:
        """
        Get all products for local synchronization.

        Args:
            branch_id: Optional filter by branch ID
            category_id: Optional filter by category ID
            available_only: Only return available products
            since: si se indica, solo se devuelven productos nuevos/modificados
                después de esta fecha (sync incremental). Omítelo para el catálogo completo.
            jwt: Optional JWT for authenticated requests
        """
        apply_optional_jwt(jwt, info)

        # Get products based on filters
        if branch_id:
            all_products = await products_repo.get_by_branch(branch_id)
        elif category_id:
            all_products = await products_repo.get_by_category(category_id)
        elif available_only:
            all_products = await products_repo.get_available()
        else:
            # Get all products
            all_products = await products_repo.get_all()

        # Excluir productos de sucursales/negocios inactivos o no aprobados,
        # y (si aplica) los que no cambiaron desde el último sync incremental
        _, active_branch_ids = await _get_active_business_and_branch_ids()
        all_products = [
            product
            for product in all_products
            if str(product.branchId) in active_branch_ids
            and _changed_since(product, since)
        ]

        # Convert to sync type
        result = []
        for product in all_products:
            product_sync = ProductSyncType(
                id=str(product.id),
                branchId=str(product.branchId),
                name=product.name,
                description=product.description,
                weight=product.weight,
                price=product.price,
                currency=product.currency,
                image=product.image,
                availability=product.availability,
                categoryId=str(product.categoryId) if product.categoryId else None,
                variantListIds=[str(vid) for vid in product.variantListIds],
                createdAt=product.createdAt,
            )
            result.append(product_sync)

        return result

    @strawberry.field(
        description="Sincronizar imágenes con URLs para diferentes calidades (200x200, 720x540, 1080x1350, 1440x1800, original)"
    )
    async def sync_images(
        self,
        info: Info,
        entity_type: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
        qualities: Optional[List[ImageQuality]] = None,
        since: Optional[datetime] = None,
        jwt: Optional[str] = None,
    ) -> List[ImageSyncType]:
        """
        Get image URLs for different quality levels for synchronization.

        Args:
            entity_type: Filter by entity type ("business", "branch", "product")
            entity_ids: Filter by specific entity IDs
            qualities: List of quality levels to include (default: [MUY_BAJA, BAJA, MEDIA, ALTA, ORIGINAL])
            since: si se indica, solo se devuelven imágenes de entidades nuevas/
                modificadas después de esta fecha (sync incremental).
            jwt: Optional JWT for authenticated requests

        Quality levels:
        - MUY_BAJA: 200x200 thumbnail (stored as {filename}_thumbnail_muy_baja.webp)
        - BAJA: 720x540 thumbnail (stored as {filename}_thumbnail.webp)
        - MEDIA: 1080x1350 thumbnail (stored as {filename}_thumbnail_media.webp)
        - ALTA: 1440x1800 thumbnail (stored as {filename}_thumbnail_alta.webp)
        - ORIGINAL: Original full-size image

        Thumbnails are automatically generated when uploading images via upload_file().
        """
        apply_optional_jwt(jwt, info)

        # Default to all qualities if not specified
        if qualities is None:
            qualities = [
                ImageQuality.MUY_BAJA,
                ImageQuality.BAJA,
                ImageQuality.MEDIA,
                ImageQuality.ALTA,
                ImageQuality.ORIGINAL,
            ]

        result = []

        # Collect images based on entity type
        images_to_sync = []

        # Excluir imágenes de negocios/sucursales inactivos o no aprobados
        active_business_ids, active_branch_ids = (
            await _get_active_business_and_branch_ids()
        )

        if entity_type is None or entity_type == "business":
            # Get business images
            if entity_ids:
                businesses = await businesses_repo.get_by_ids(entity_ids)
            else:
                businesses = await businesses_repo.get_all()
            businesses = [
                b
                for b in businesses
                if str(b.id) in active_business_ids and _changed_since(b, since)
            ]

            for business in businesses:
                if business.avatar:
                    images_to_sync.append(
                        {
                            "entity_id": str(business.id),
                            "entity_type": "business",
                            "image_path": business.avatar,
                        }
                    )

        if entity_type is None or entity_type == "branch":
            # Get branch images
            if entity_ids:
                branches = []
                for eid in entity_ids:
                    branch = await branches_repo.get_by_id(eid)
                    if branch:
                        branches.append(branch)
            else:
                # Get all branches
                all_businesses = await businesses_repo.get_all()
                branches = []
                for business in all_businesses:
                    branch_list = await branches_repo.get_by_business(
                        str(business.id)
                    )
                    branches.extend(branch_list)
            branches = [
                b
                for b in branches
                if str(b.id) in active_branch_ids and _changed_since(b, since)
            ]

            for branch in branches:
                if branch.avatar:
                    images_to_sync.append(
                        {
                            "entity_id": str(branch.id),
                            "entity_type": "branch",
                            "image_path": branch.avatar,
                        }
                    )
                if branch.coverImage:
                    images_to_sync.append(
                        {
                            "entity_id": str(branch.id),
                            "entity_type": "branch",
                            "image_path": branch.coverImage,
                        }
                    )

        if entity_type is None or entity_type == "product":
            # Get product images
            if entity_ids:
                products = await products_repo.get_by_ids(entity_ids)
            else:
                products = await products_repo.get_all()
            products = [
                p
                for p in products
                if str(p.branchId) in active_branch_ids and _changed_since(p, since)
            ]

            for product in products:
                if product.image:
                    images_to_sync.append(
                        {
                            "entity_id": str(product.id),
                            "entity_type": "product",
                            "image_path": product.image,
                        }
                    )

        # Generate URLs for each image
        for img in images_to_sync:
            urls = ImageUrlType()

            # Generate presigned URLs based on requested qualities
            for quality in qualities:
                if quality == ImageQuality.MUY_BAJA:
                    urls.muy_baja = get_public_url(
                        get_image_variant_path(img["image_path"], "muy_baja")
                    )
                elif quality == ImageQuality.BAJA:
                    urls.baja = get_public_url(
                        get_image_variant_path(img["image_path"], "baja")
                    )
                elif quality == ImageQuality.MEDIA:
                    urls.media = get_public_url(
                        get_image_variant_path(img["image_path"], "media")
                    )
                elif quality == ImageQuality.ALTA:
                    urls.alta = get_public_url(
                        get_image_variant_path(img["image_path"], "alta")
                    )
                elif quality == ImageQuality.ORIGINAL:
                    urls.original = get_public_url(img["image_path"])

            image_sync = ImageSyncType(
                entity_id=img["entity_id"],
                entity_type=img["entity_type"],
                image_path=img["image_path"],
                urls=urls,
            )
            result.append(image_sync)

        return result
