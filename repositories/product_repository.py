"""Product repository for database operations."""
from typing import List, Optional, Dict, Any
from clients import get_qdrant_client
from models import Product
from qdrant_client.http import models as qdrant_models


class ProductRepository:
    qdrant_collection_name = "products"

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
