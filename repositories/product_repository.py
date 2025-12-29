"""Product repository for database operations."""
from typing import List, Optional, Dict, Any
import uuid
from clients import get_qdrant_client
from models import Product
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService


class ProductRepository:
    qdrant_collection_name = "products"

    async def create(self, product: Product) -> Product:
        """Create a new product in Qdrant."""
        try:
            embedding_service = GeminiEmbeddingService()
            text_to_embed = f"{product.name} {product.description or ''}"
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()

            payload = {
                "metadata": {
                    "mongo_id": str(product.id),
                    "branchId": product.branchId,
                    "name": product.name,
                    "description": product.description,
                    "weight": product.weight,
                    "price": product.price,
                    "currency": product.currency,
                    "image": product.image,
                    "availability": product.availability,
                    "categoryId": product.categoryId,
                    "createdAt": product.createdAt.isoformat() if product.createdAt else None
                }
            }

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload
            )

            await qdrant_client.upsert(
                collection_name=self.qdrant_collection_name,
                points=[point]
            )

            return product
        except Exception as e:
            print(f"Error creating product in Qdrant: {e}")
            raise e

    async def update(self, product_id: str, updates: Dict[str, Any]) -> Optional[Product]:
        """Update a product in Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Find the point by mongo_id
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=product_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True
            )

            points, _ = result
            if not points:
                return None

            point = points[0]
            metadata = point.payload.get("metadata", {})

            # Update metadata with new values
            for key, value in updates.items():
                metadata[key] = value

            # Regenerate embedding if name or description changed
            if "name" in updates or "description" in updates:
                embedding_service = GeminiEmbeddingService()
                text_to_embed = f"{metadata.get('name', '')} {metadata.get('description', '')}"
                new_vector = embedding_service.generate_embedding(text_to_embed)
            else:
                new_vector = point.vector

            # Update the point
            updated_point = PointStruct(
                id=point.id,
                vector=new_vector,
                payload={"metadata": metadata}
            )

            await qdrant_client.upsert(
                collection_name=self.qdrant_collection_name,
                points=[updated_point]
            )

            return self._point_to_product(updated_point)
        except Exception as e:
            print(f"Error updating product {product_id}: {e}")
            raise e

    async def update_field(self, product_id: str, field: str, value: Any) -> Optional[Product]:
        """Update a single field of a product."""
        return await self.update(product_id, {field: value})

    async def delete(self, product_id: str) -> bool:
        """Delete a product from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Find the point by mongo_id to get its UUID
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=product_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False
            )

            points, _ = result
            if not points:
                return False

            # Delete by point ID
            await qdrant_client.delete(
                collection_name=self.qdrant_collection_name,
                points_selector=qdrant_models.PointIdsList(
                    points=[points[0].id]
                )
            )

            return True
        except Exception as e:
            print(f"Error deleting product {product_id}: {e}")
            return False

    async def get_all(self) -> List[Product]:
        """Get all products from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []
            offset = None

            # Scroll through all points in Qdrant
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    product = self._point_to_product(point)
                    if product:
                        products.append(product)

                if offset is None:
                    break

            return products

        except Exception as e:
            print(f"Error fetching all products from Qdrant: {e}")
            return []

    async def get_by_id(self, product_id: str) -> Optional[Product]:
        """Get product by ID from Qdrant (searches by metadata.mongo_id)."""
        try:
            qdrant_client = get_qdrant_client()

            # Search for point with this mongo_id in metadata
            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.mongo_id",
                            match=qdrant_models.MatchValue(value=product_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )

            points, _ = result

            if points:
                return self._point_to_product(points[0])

            return None

        except Exception as e:
            print(f"Error fetching product {product_id} from Qdrant: {e}")
            return None

    async def search(self, query: str) -> List[Product]:
        """Search products by name or description in Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []
            offset = None
            query_lower = query.lower()

            # Since Qdrant doesn't have native text search on payload,
            # we need to scroll through all products and filter client-side
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    metadata = point.payload.get("metadata", {})
                    name = metadata.get("name", "").lower()
                    description = metadata.get("description", "").lower()

                    # Check if query matches name or description
                    if query_lower in name or query_lower in description:
                        product = self._point_to_product(point)
                        if product:
                            products.append(product)

                if offset is None:
                    break

            return products

        except Exception as e:
            print(f"Error searching products in Qdrant: {e}")
            return []

    async def get_by_branch(self, branch_id: str) -> List[Product]:
        """Get products by branch ID from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []
            offset = None

            # Filter by metadata.branchId
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.branchId",
                                match=qdrant_models.MatchValue(value=branch_id)
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    product = self._point_to_product(point)
                    if product:
                        products.append(product)

                if offset is None:
                    break

            return products

        except Exception as e:
            print(f"Error fetching products by branch from Qdrant: {e}")
            return []

    async def get_available(self) -> List[Product]:
        """Get available products from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []
            offset = None

            # Filter by metadata.availability = True
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.availability",
                                match=qdrant_models.MatchValue(value=True)
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    product = self._point_to_product(point)
                    if product:
                        products.append(product)

                if offset is None:
                    break

            return products

        except Exception as e:
            print(f"Error fetching available products from Qdrant: {e}")
            return []

    async def get_by_ids(self, product_ids: List[str]) -> List[Product]:
        """Get products by IDs from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []

            for product_id in product_ids:
                # Search for point with this mongo_id in metadata
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.mongo_id",
                                match=qdrant_models.MatchValue(value=product_id)
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False
                )

                points, _ = result

                if points:
                    product = self._point_to_product(points[0])
                    if product:
                        products.append(product)

            return products

        except Exception as e:
            print(f"Error fetching products from Qdrant: {e}")
            return []

    async def get_by_category(self, category_id: str) -> List[Product]:
        """Get products by category ID from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()
            products = []
            offset = None

            # Filter by metadata.categoryId
            while True:
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.categoryId",
                                match=qdrant_models.MatchValue(value=category_id)
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                points, offset = result

                if not points:
                    break

                for point in points:
                    product = self._point_to_product(point)
                    if product:
                        products.append(product)

                if offset is None:
                    break

            return products

        except Exception as e:
            print(f"Error fetching products by category from Qdrant: {e}")
            return []

    @staticmethod
    def _point_to_product(point) -> Optional[Product]:
        """Convert a Qdrant point to a Product model."""
        try:
            metadata = point.payload.get("metadata", {})

            # Reconstruct Product from metadata
            product_data = {
                "_id": metadata.get("mongo_id"),
                "name": metadata.get("name"),
                "description": metadata.get("description"),
                "price": metadata.get("price"),
                "currency": metadata.get("currency", "USD"),
                "weight": metadata.get("weight"),
                "availability": metadata.get("availability", False),
                "image": metadata.get("image"),
                "branchId": metadata.get("branchId"),
                "categoryId": metadata.get("categoryId"),
                "createdAt": metadata.get("createdAt")
            }

            return Product(**product_data)

        except Exception as e:
            print(f"Error converting point to product: {e}")
            return None
