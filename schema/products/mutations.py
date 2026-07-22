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
from utils.currency import branch_accepts_currency
from utils.graphql_auth import apply_optional_jwt
from utils.serialization import to_strawberry_dict
from utils.s3 import delete_file
from services.access_checker import access_checker
from services.qdrant_indexing_service import qdrant_indexing_service


async def _validate_variant_lists_belong_to_business(
    variant_lists: list,
    business_id: str,
) -> None:
    """Validate that each variant list belongs to a branch of the given business."""
    if not variant_lists:
        return

    branch_ids = list({str(vl.branchId) for vl in variant_lists})
    branches = await branches_repo.get_by_ids(branch_ids)
    business_by_branch = {str(branch.id): str(branch.businessId) for branch in branches}

    for vl in variant_lists:
        variant_branch_id = str(vl.branchId)
        variant_branch_business_id = business_by_branch.get(variant_branch_id)

        if not variant_branch_business_id:
            raise Exception(
                f"La sucursal de la lista de variantes '{vl.name}' no fue encontrada"
            )

        if variant_branch_business_id != str(business_id):
            raise Exception(
                f"La lista de variantes '{vl.name}' no pertenece al negocio de esta sucursal"
            )


async def _delete_image_if_unreferenced(
    image_path: Optional[str],
    exclude_product_id: Optional[str] = None,
) -> None:
    """Delete product image only when no other product still references it."""
    if not image_path:
        return

    is_shared = await products_repo.has_other_products_with_image(
        image_path=image_path,
        exclude_product_id=exclude_product_id,
    )
    if not is_shared:
        await delete_file(image_path)


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
            # DEBUG: Log user_id and branchId
            print(f"[DEBUG] create_product - user_id: {user_id} (type: {type(user_id)})")
            print(f"[DEBUG] create_product - branchId: {input.branchId}")

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

        # Validate variantListIds if provided
        variant_list_ids = []
        if input.variantListIds:
            from repositories import variant_lists_repo
            
            # Get branch to validate businessId
            if not branch:
                branch = await branches_repo.get_by_id(target_branch_id)
                if not branch:
                    raise Exception("Sucursal no encontrada")
            
            # Get business to validate ownership
            business = await businesses_repo.get_by_id(branch.businessId)
            if not business:
                raise Exception("Negocio no encontrado")
            
            variant_lists = await variant_lists_repo.get_by_ids(input.variantListIds)
            if len(variant_lists) != len(input.variantListIds):
                raise Exception("Una o más listas de variantes no fueron encontradas")
            
            await _validate_variant_lists_belong_to_business(
                variant_lists=variant_lists,
                business_id=str(business.id),
            )
            
            variant_list_ids = [ObjectId(vid) for vid in input.variantListIds]

        # Validate that the branch actually accepts payments in this currency
        if not branch_accepts_currency(getattr(branch, "acceptedCurrency", None), input.currency):
            raise Exception(
                f"La sucursal no acepta pagos en {input.currency}. "
                f"Moneda(s) aceptada(s): {branch.acceptedCurrency or 'USD'}"
            )

        # Create product
        product_id = ObjectId()
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
            variantListIds=variant_list_ids,
            createdAt=datetime.now()
        )

        # Step 1: Create in MongoDB first
        created_product = await products_repo.create(product)

        # Step 2: Index in Qdrant for vector search
        await qdrant_indexing_service.index_product(created_product)

        return ProductType(**to_strawberry_dict(created_product))

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

        branch = None

        # Validate variantListIds if provided
        if input.variantListIds is not None:
            from repositories import variant_lists_repo

            # Get branch to validate businessId
            branch = await branches_repo.get_by_id(product.branchId)
            if not branch:
                raise Exception("Sucursal no encontrada")

            # Get business to validate ownership
            business = await businesses_repo.get_by_id(branch.businessId)
            if not business:
                raise Exception("Negocio no encontrado")

            variant_lists = await variant_lists_repo.get_by_ids(input.variantListIds)
            if len(variant_lists) != len(input.variantListIds):
                raise Exception("Una o más listas de variantes no fueron encontradas")

            await _validate_variant_lists_belong_to_business(
                variant_lists=variant_lists,
                business_id=str(business.id),
            )

        # Validate that the branch actually accepts payments in this currency
        if input.currency is not None:
            if branch is None:
                branch = await branches_repo.get_by_id(product.branchId)
                if not branch:
                    raise Exception("Sucursal no encontrada")
            if not branch_accepts_currency(getattr(branch, "acceptedCurrency", None), input.currency):
                raise Exception(
                    f"La sucursal no acepta pagos en {input.currency}. "
                    f"Moneda(s) aceptada(s): {branch.acceptedCurrency or 'USD'}"
                )

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
        if input.variantListIds is not None:
            updates["variantListIds"] = [ObjectId(vid) for vid in input.variantListIds]
        old_image_path = product.image
        image_changed = input.image is not None and input.image != product.image
        if image_changed:
            updates["image"] = input.image

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update product
        updated_product = await products_repo.update(product_id, updates)
        if not updated_product:
            raise Exception("Error al actualizar el producto")

        # Delete previous image only if it is no longer referenced.
        if image_changed and old_image_path:
            await _delete_image_if_unreferenced(
                image_path=old_image_path,
                exclude_product_id=product_id,
            )

        # Re-index in Qdrant if name or description changed
        if "name" in updates or "description" in updates:
            await qdrant_indexing_service.index_product(updated_product)

        return ProductType(**to_strawberry_dict(updated_product))

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

        # Delete product
        success = await products_repo.delete(product_id)
        if not success:
            raise Exception("Error al eliminar el producto")

        # Delete image from S3 only if no other product still references it.
        await _delete_image_if_unreferenced(image_path=product.image)

        return True
