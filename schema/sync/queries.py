"""GraphQL query resolvers for synchronization."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, businesses_repo, products_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import generate_presigned_url, get_image_variant_path

from .types import (
    BusinessSyncType,
    BranchSyncType,
    CoordinatesSyncType,
    ImageQuality,
    ImageSyncType,
    ImageUrlType,
    ProductSyncType,
)


@strawberry.type
class SyncQuery:
    @strawberry.field(
        description="Sincronizar negocios con sus branches (excluye datos sensibles como managerIds y ownerId)"
    )
    async def sync_businesses_with_branches(
        self, info: Info, jwt: Optional[str] = None
    ) -> List[BusinessSyncType]:
        """
        Get all businesses with their branches for local synchronization.

        This query excludes sensitive data such as:
        - ownerId
        - managerIds
        - Payment account details
        - Wallet information

        Suitable for public/offline caching.
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

            # Convert branches to sync type (excluding sensitive data)
            branch_sync_list = []
            for branch in branches:
                if not branch.isActive:
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
                    schedule=branch.schedule,
                    isActive=branch.isActive,
                    status=branch.status,
                    avatar=branch.avatar,
                    coverImage=branch.coverImage,
                    socialMedia=branch.socialMedia,
                    tipos=branch.tipos,
                    useAppMessaging=branch.useAppMessaging,
                    vehicles=branch.vehicles,
                    deliveryRadius=branch.deliveryRadius,
                    createdAt=branch.createdAt,
                )
                branch_sync_list.append(branch_sync)

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
        jwt: Optional[str] = None,
    ) -> List[ProductSyncType]:
        """
        Get all products for local synchronization.

        Args:
            branch_id: Optional filter by branch ID
            category_id: Optional filter by category ID
            available_only: Only return available products
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
        jwt: Optional[str] = None,
    ) -> List[ImageSyncType]:
        """
        Get image URLs for different quality levels for synchronization.

        Args:
            entity_type: Filter by entity type ("business", "branch", "product")
            entity_ids: Filter by specific entity IDs
            qualities: List of quality levels to include (default: [MUY_BAJA, BAJA, MEDIA, ALTA, ORIGINAL])
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

        if entity_type is None or entity_type == "business":
            # Get business images
            if entity_ids:
                businesses = await businesses_repo.get_by_ids(entity_ids)
            else:
                businesses = await businesses_repo.get_all()

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
                    urls.muy_baja = generate_presigned_url(
                        get_image_variant_path(img["image_path"], "muy_baja")
                    )
                elif quality == ImageQuality.BAJA:
                    urls.baja = generate_presigned_url(
                        get_image_variant_path(img["image_path"], "baja")
                    )
                elif quality == ImageQuality.MEDIA:
                    urls.media = generate_presigned_url(
                        get_image_variant_path(img["image_path"], "media")
                    )
                elif quality == ImageQuality.ALTA:
                    urls.alta = generate_presigned_url(
                        get_image_variant_path(img["image_path"], "alta")
                    )
                elif quality == ImageQuality.ORIGINAL:
                    urls.original = generate_presigned_url(img["image_path"])

            image_sync = ImageSyncType(
                entity_id=img["entity_id"],
                entity_type=img["entity_type"],
                image_path=img["image_path"],
                urls=urls,
            )
            result.append(image_sync)

        return result
