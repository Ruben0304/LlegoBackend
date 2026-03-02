"""GraphQL query resolvers for synchronization."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, businesses_repo, products_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import generate_presigned_url

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
            branches = await branches_repo.get_by_business_id(str(business.id))

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
        description="Sincronizar imágenes con URLs para diferentes calidades (baja, buena, mejor)"
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
            qualities: List of quality levels to include (default: all)
            jwt: Optional JWT for authenticated requests

        Note: Currently generates presigned URLs for the original image.
        To support different quality levels, you need to:
        1. Generate image thumbnails during upload (e.g., 300x300, 800x800, original)
        2. Store them in S3 with naming convention (e.g., "image_300x300.jpg", "image_800x800.jpg")
        3. Update this resolver to return appropriate URLs for each quality level

        For now, this returns the same URL for all quality levels (original).
        Consider using AWS Lambda@Edge or CloudFront with image optimization.
        """
        apply_optional_jwt(jwt, info)

        # Default to all qualities if not specified
        if qualities is None:
            qualities = [ImageQuality.BAJA, ImageQuality.BUENA, ImageQuality.MEJOR]

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
                    branch_list = await branches_repo.get_by_business_id(
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
            # TODO: Implement different quality levels
            # For now, return the same URL for all qualities (original image)
            # In production, you should generate thumbnails during upload
            # and store them with naming conventions like:
            # - products/123_baja.jpg (300x300)
            # - products/123_buena.jpg (800x800)
            # - products/123_mejor.jpg (original)

            urls = ImageUrlType()

            # Generate presigned URLs based on requested qualities
            base_url = generate_presigned_url(img["image_path"])

            for quality in qualities:
                if quality == ImageQuality.BAJA:
                    # TODO: Load thumbnail version (e.g., _300x300)
                    urls.baja = base_url
                elif quality == ImageQuality.BUENA:
                    # TODO: Load medium version (e.g., _800x800)
                    urls.buena = base_url
                elif quality == ImageQuality.MEJOR:
                    # Original quality
                    urls.mejor = base_url

            image_sync = ImageSyncType(
                entity_id=img["entity_id"],
                entity_type=img["entity_type"],
                image_path=img["image_path"],
                urls=urls,
            )
            result.append(image_sync)

        return result
