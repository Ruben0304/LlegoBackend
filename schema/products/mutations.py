"""GraphQL mutations for Product entity."""
import strawberry
from typing import Optional
from datetime import datetime
from strawberry.types import Info
from bson import ObjectId

from .types import ProductType
from .inputs import CreateProductInput, UpdateProductInput
from domain.models import Product
from repositories import products_repo, branches_repo, businesses_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file
from services.qdrant_indexing_service import qdrant_indexing_service
from services.access_checker import access_checker


@strawberry.type
class ProductMutation:
    @strawberry.mutation(description="Crear un nuevo producto")
    async def create_product(
        self,
        info: Info,
        input: CreateProductInput,
        jwt: Optional[str] = None
    ) -> ProductType:
        """
        Create a new product. Image should be uploaded first via POST /upload/product/image.
        Either branchId or businessId must be provided. If only businessId is provided,
        the product will be assigned to the first branch of that business.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Validate that at least one of branchId or businessId is provided
        if not input.branchId and not input.businessId:
            raise Exception("Se requiere branchId o businessId")

        branch = None
        business = None

        if input.branchId:
            # Verify branch exists and user has access
            await access_checker.require_branch_access(user_id, input.branchId)

            branch = await branches_repo.get_by_id(input.branchId)
            if not branch:
                raise Exception("Sucursal no encontrada")

            target_branch_id = input.branchId
        else:
            # businessId provided, find the first branch
            await access_checker.require_business_access(user_id, input.businessId)

            business = await businesses_repo.get_by_id(input.businessId)
            if not business:
                raise Exception("Negocio no encontrado")

            # Get branches for this business
            branches = await branches_repo.get_by_business(input.businessId)
            if not branches:
                raise Exception("El negocio no tiene sucursales. Cree una sucursal primero")

            # Use the first branch
            branch = branches[0]
            target_branch_id = branch.id

        # Validate categoryId if provided
        if input.categoryId:
            from repositories import product_categories_repo
            category = await product_categories_repo.get_by_id(input.categoryId)
            if not category:
                raise Exception(f"Categoría con ID '{input.categoryId}' no encontrada")

        # Create product
        product_id = str(ObjectId())
        product = Product(
            _id=product_id,
            branchId=target_branch_id,
            name=input.name,
            description=input.description,
            weight=input.weight or "",
            price=input.price,
            currency=input.currency,
            image=input.image,
            availability=True,
            categoryId=input.categoryId,
            createdAt=datetime.now()
        )

        # Step 1: Create in MongoDB first
        created_product = await products_repo.create(product)

        # Step 2: Index in Qdrant with the MongoDB ID
        await qdrant_indexing_service.index_product(created_product)

        return ProductType(**created_product.model_dump())

    @strawberry.mutation(description="Actualizar un producto")
    async def update_product(
        self,
        info: Info,
        product_id: str,
        input: UpdateProductInput,
        jwt: Optional[str] = None
    ) -> ProductType:
        """
        Update product data. For new image, upload via POST /upload/product/image first.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify product exists
        product = await products_repo.get_by_id(product_id)
        if not product:
            raise Exception("Producto no encontrado")

        # Verify user has access to the branch
        await access_checker.require_branch_access(user_id, product.branchId)

        # Validate categoryId if provided
        if input.categoryId is not None:
            from repositories import product_categories_repo
            category = await product_categories_repo.get_by_id(input.categoryId)
            if not category:
                raise Exception(f"Categoría con ID '{input.categoryId}' no encontrada")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.description is not None:
            updates["description"] = input.description
        if input.price is not None:
            updates["price"] = input.price
        if input.currency is not None:
            updates["currency"] = input.currency
        if input.weight is not None:
            updates["weight"] = input.weight
        if input.availability is not None:
            updates["availability"] = input.availability
        if input.categoryId is not None:
            updates["categoryId"] = input.categoryId
        if input.image is not None:
            # Delete old image if exists
            if product.image:
                await delete_file(product.image)
            updates["image"] = input.image

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update product
        updated_product = await products_repo.update(product_id, updates)
        if not updated_product:
            raise Exception("Error al actualizar el producto")

        return ProductType(**updated_product.model_dump())

    @strawberry.mutation(description="Eliminar un producto")
    async def delete_product(
        self,
        info: Info,
        product_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """Delete a product."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify product exists
        product = await products_repo.get_by_id(product_id)
        if not product:
            raise Exception("Producto no encontrado")

        # Verify user has access to the branch
        await access_checker.require_branch_access(user_id, product.branchId)

        # Delete image from S3
        if product.image:
            from utils.s3 import delete_file
            await delete_file(product.image)

        # Delete product
        success = await products_repo.delete(product_id)
        if not success:
            raise Exception("Error al eliminar el producto")

        return True
